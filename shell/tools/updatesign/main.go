// Command updatesign prepares the files of a release for the in-app updater
// (see internal/update): it copies the program packages under their release
// names, writes update.json and signs it with the project's private key.
//
//	go run ./tools/updatesign -key ~/grmod-update-private.key -version 0.7.1 \
//	    -notes-zh "……" -notes-en "..." \
//	    -windows dist/GRMod.exe -mac dist/GRMod-mac.zip -out dist/release
//
// Upload everything in -out to the GitHub release (and to any mirror). The
// release must be the latest one, since the program looks under
// releases/latest/download/.
//
//	go run ./tools/updatesign -keygen -key grmod-update-private.key
//
// creates a new key pair and prints the public key for updates.go. The
// private key never goes into the repository; keep a backup: without it no
// installed copy will accept another update.
package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strings"
	"time"

	"grmod/shell/internal/update"
)

func main() {
	keyPath := flag.String("key", "", "private key file (base64 Ed25519 seed)")
	keygen := flag.Bool("keygen", false, "create a new key pair in -key and print the public key")
	version := flag.String("version", "", "release version, e.g. 0.7.1")
	date := flag.String("date", time.Now().Format("2006-01-02"), "release date")
	notesZh := flag.String("notes-zh", "", "release notes, Chinese")
	notesEn := flag.String("notes-en", "", "release notes, English")
	page := flag.String("page", "", "release page (default: the GitHub release of this version)")
	win := flag.String("windows", "", "Windows program (GRMod.exe)")
	mac := flag.String("mac", "", "macOS bundle zip (GRMod-mac.zip)")
	linux := flag.String("linux", "", "Linux development build (tests only)")
	out := flag.String("out", "", "output directory")
	flag.Parse()
	log.SetFlags(0)

	if *keyPath == "" {
		log.Fatal("updatesign: -key is required")
	}
	if *keygen {
		if _, err := os.Stat(*keyPath); err == nil {
			log.Fatalf("updatesign: %s exists; not overwriting a key", *keyPath)
		}
		pub, priv, err := ed25519.GenerateKey(nil)
		if err != nil {
			log.Fatal(err)
		}
		if err := os.WriteFile(*keyPath, []byte(base64.StdEncoding.EncodeToString(priv.Seed())+"\n"), 0o600); err != nil {
			log.Fatal(err)
		}
		fmt.Println(base64.StdEncoding.EncodeToString(pub))
		return
	}
	if *version == "" || *out == "" || (*win == "" && *mac == "" && *linux == "") {
		log.Fatal("updatesign: -version, -out and at least one package are required")
	}
	seed, err := os.ReadFile(*keyPath)
	if err != nil {
		log.Fatal(err)
	}
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(string(seed)))
	if err != nil || len(raw) != ed25519.SeedSize {
		log.Fatal("updatesign: the key file does not hold a base64 Ed25519 seed")
	}
	priv := ed25519.NewKeyFromSeed(raw)
	if *page == "" {
		*page = "https://github.com/Maxwooow/Ricoh-GRMod/releases/tag/v" + *version
	}
	m := update.Manifest{App: update.AppName, Version: *version, Date: *date, Page: *page, Files: map[string]update.File{}}
	if *notesZh != "" || *notesEn != "" {
		m.Notes = map[string]string{}
		if *notesZh != "" {
			m.Notes["zh"] = *notesZh
		}
		if *notesEn != "" {
			m.Notes["en"] = *notesEn
		}
	}
	if err := os.MkdirAll(*out, 0o755); err != nil {
		log.Fatal(err)
	}
	add := func(platform, src, name string) {
		if src == "" {
			return
		}
		f, err := copyHash(src, filepath.Join(*out, name))
		if err != nil {
			log.Fatal(err)
		}
		f.Name = name
		m.Files[platform] = f
		fmt.Printf("%-14s %s  %d bytes  sha256 %s\n", platform, name, f.Size, f.SHA256)
	}
	add(update.PlatformWindows, *win, "GRMod-"+*version+".exe")
	add(update.PlatformMac, *mac, "GRMod-"+*version+"-mac.zip")
	add("linux-amd64", *linux, "grmod-"+*version+"-linux")

	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		log.Fatal(err)
	}
	data = append(data, '\n')
	sig := update.Sign(data, priv)
	// Check the result the way the program will.
	if _, err := update.ParseManifest(data, sig, priv.Public().(ed25519.PublicKey)); err != nil {
		log.Fatalf("updatesign: the manifest does not verify: %v", err)
	}
	if err := os.WriteFile(filepath.Join(*out, update.ManifestName), data, 0o644); err != nil {
		log.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(*out, update.SignatureName), []byte(sig+"\n"), 0o644); err != nil {
		log.Fatal(err)
	}
	fmt.Printf("public key     %s\n", base64.StdEncoding.EncodeToString(priv.Public().(ed25519.PublicKey)))
	fmt.Printf("written        %s, %s\n", update.ManifestName, update.SignatureName)
}

func copyHash(src, dst string) (update.File, error) {
	in, err := os.Open(src)
	if err != nil {
		return update.File{}, err
	}
	defer in.Close()
	out, err := os.Create(dst)
	if err != nil {
		return update.File{}, err
	}
	h := sha256.New()
	n, err := io.Copy(io.MultiWriter(out, h), in)
	if cerr := out.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		return update.File{}, err
	}
	return update.File{Size: n, SHA256: hex.EncodeToString(h.Sum(nil))}, nil
}
