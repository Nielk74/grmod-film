package update

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// Release is one published release as the release site describes it, for
// showing what changed ("what's new"). Nothing here is used to install
// anything, so it does not need the signature.
type Release struct {
	Version string `json:"version"`
	Name    string `json:"name,omitempty"`
	// Date is the publication date, YYYY-MM-DD.
	Date string `json:"date,omitempty"`
	// Body is the release text as written on the release page (Markdown).
	Body string `json:"body"`
	Page string `json:"page,omitempty"`
}

const (
	maxReleases     = 30
	maxReleasesJSON = 4 << 20
	maxReleaseBody  = 64 << 10
)

// FetchReleases reads the published releases, newest first, from a GitHub
// "list releases" address (https://api.github.com/repos/OWNER/REPO/releases).
// Drafts, pre-releases and releases whose tag is not a version are left out.
func FetchReleases(ctx context.Context, client *http.Client, address, agent string) ([]Release, error) {
	if client == nil {
		client = http.DefaultClient
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", agent)
	res, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer res.Body.Close()
	if res.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("%s: %s", address, res.Status)
	}
	data, err := io.ReadAll(io.LimitReader(res.Body, maxReleasesJSON+1))
	if err != nil {
		return nil, err
	}
	if len(data) > maxReleasesJSON {
		return nil, fmt.Errorf("%s: too large", address)
	}
	var raw []struct {
		Tag        string `json:"tag_name"`
		Name       string `json:"name"`
		Body       string `json:"body"`
		Page       string `json:"html_url"`
		Published  string `json:"published_at"`
		Draft      bool   `json:"draft"`
		Prerelease bool   `json:"prerelease"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("unreadable release list: %w", err)
	}
	out := []Release{}
	for _, r := range raw {
		if r.Draft || r.Prerelease {
			continue
		}
		if _, ok := parseVersion(r.Tag); !ok {
			continue
		}
		body := r.Body
		if len(body) > maxReleaseBody {
			body = body[:maxReleaseBody]
		}
		rel := Release{Version: strings.TrimPrefix(strings.TrimSpace(r.Tag), "v"), Name: r.Name, Body: strings.ReplaceAll(body, "\r\n", "\n")}
		if len(r.Published) >= 10 {
			rel.Date = r.Published[:10]
		}
		if strings.HasPrefix(r.Page, "https://") {
			rel.Page = r.Page
		}
		out = append(out, rel)
		if len(out) == maxReleases {
			break
		}
	}
	// Newest first by version (the list is by date, which can differ for a re-published release).
	for i := 1; i < len(out); i++ {
		for j := i; j > 0 && Newer(out[j].Version, out[j-1].Version); j-- {
			out[j], out[j-1] = out[j-1], out[j]
		}
	}
	return out, nil
}
