// SPDX-License-Identifier: GPL-2.0-only
// Power-off pictures of the film pack, drawn in code (720 x 480). pictures.ps1 compiles and runs it.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.Runtime.InteropServices;

public static class FilmPackPictures
{
    const int W = 720, H = 480;

    public static string[] Names = { "Star Trails", "Film Strip", "Contours", "Aperture", "Synthwave", "Bauhaus", "Great Wave", "Good Night" };

    public static void Run(string outDir)
    {
        Directory.CreateDirectory(outDir);
        Func<Graphics, Bitmap, int>[] draw = { StarTrails, FilmStrip, Contours, Aperture, Synthwave, Bauhaus, GreatWave, GoodNight };
        for (int k = 0; k < draw.Length; k++)
        {
            using (Bitmap bmp = new Bitmap(W, H, PixelFormat.Format24bppRgb))
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.TextRenderingHint = TextRenderingHint.AntiAlias;
                g.CompositingQuality = CompositingQuality.HighQuality;
                draw[k](g, bmp);
                string name = (k + 1) + "-" + Names[k].Replace(" ", "-");
                bmp.Save(Path.Combine(outDir, name + ".png"), ImageFormat.Png);
                BitmapData d = bmp.LockBits(new Rectangle(0, 0, W, H), ImageLockMode.ReadOnly, bmp.PixelFormat);
                byte[] buf = new byte[d.Stride * H];
                Marshal.Copy(d.Scan0, buf, 0, buf.Length);
                bmp.UnlockBits(d);
                File.WriteAllBytes(Path.Combine(outDir, name + ".bgr"), buf);
            }
        }
    }

    // ------------------------------------------------------------------ helpers

    static Color C(int r, int g, int b) { return Color.FromArgb(r, g, b); }
    static Color A(int a, Color c) { return Color.FromArgb(a, c); }

    static void Vertical(Graphics g, RectangleF r, Color[] colors, float[] stops)
    {
        using (LinearGradientBrush b = new LinearGradientBrush(new PointF(0, r.Top - 1), new PointF(0, r.Bottom + 1), colors[0], colors[colors.Length - 1]))
        {
            ColorBlend cb = new ColorBlend();
            cb.Colors = colors; cb.Positions = stops;
            b.InterpolationColors = cb;
            g.FillRectangle(b, r);
        }
    }

    static void Text(Graphics g, string s, string font, float size, FontStyle style, Color c, float x, float y, float spacing, bool centre)
    {
        using (Font f = new Font(font, size, style, GraphicsUnit.Pixel))
        using (SolidBrush b = new SolidBrush(c))
        {
            if (spacing == 0)
            {
                SizeF sz = g.MeasureString(s, f, PointF.Empty, StringFormat.GenericTypographic);
                g.DrawString(s, f, b, centre ? x - sz.Width / 2 : x, y, StringFormat.GenericTypographic);
                return;
            }
            float total = 0;
            foreach (char ch in s) total += g.MeasureString(ch.ToString(), f, PointF.Empty, StringFormat.GenericTypographic).Width + spacing;
            total -= spacing;
            float px = centre ? x - total / 2 : x;
            foreach (char ch in s)
            {
                g.DrawString(ch.ToString(), f, b, px, y, StringFormat.GenericTypographic);
                px += g.MeasureString(ch.ToString(), f, PointF.Empty, StringFormat.GenericTypographic).Width + spacing;
            }
        }
    }

    /** Smooth value noise, octaves summed (0..1). */
    static double Noise(double x, double y, int seed)
    {
        Func<int, int, double> h = (ix, iy) =>
        {
            unchecked
            {
                int n = ix * 374761393 + iy * 668265263 + seed * 1442695041;
                n = (n ^ (n >> 13)) * 1274126177;
                return ((n ^ (n >> 16)) & 0xffff) / 65535.0;
            }
        };
        int x0 = (int)Math.Floor(x), y0 = (int)Math.Floor(y);
        double fx = x - x0, fy = y - y0;
        double sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
        double a = h(x0, y0), b = h(x0 + 1, y0), c = h(x0, y0 + 1), d = h(x0 + 1, y0 + 1);
        return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
    }

    static double Fbm(double x, double y, int seed, int octaves)
    {
        double s = 0, amp = 0.5, tot = 0;
        for (int o = 0; o < octaves; o++) { s += amp * Noise(x, y, seed + o * 17); tot += amp; x *= 2.03; y *= 2.03; amp *= 0.5; }
        return s / tot;
    }

    static PointF[] Ridge(int seed, float baseY, float amp, float scale, int octaves)
    {
        List<PointF> p = new List<PointF>();
        p.Add(new PointF(-2, H + 2));
        for (int x = -2; x <= W + 2; x += 3) p.Add(new PointF(x, baseY - amp * (float)Fbm(x / scale, 0.5, seed, octaves)));
        p.Add(new PointF(W + 2, H + 2));
        return p.ToArray();
    }

    // ------------------------------------------------------------------ 1. star trails

    static int StarTrails(Graphics g, Bitmap bmp)
    {
        Vertical(g, new RectangleF(0, 0, W, H), new[] { C(4, 6, 18), C(10, 18, 44), C(22, 44, 78), C(70, 70, 96) }, new[] { 0f, 0.45f, 0.78f, 1f });
        Random r = new Random(7);
        PointF pole = new PointF(470, 90);
        for (int i = 0; i < 260; i++)
        {
            float rad = (float)(6 + Math.Pow(r.NextDouble(), 0.8) * 640);
            float start = (float)(r.NextDouble() * 360), sweep = 34f;
            double t = r.NextDouble();
            Color col = t < 0.15 ? C(255, 214, 170) : t < 0.35 ? C(170, 200, 255) : C(235, 240, 255);
            int alpha = 40 + r.Next(150);
            float width = r.NextDouble() < 0.08 ? 1.8f : 1.0f;
            using (Pen p = new Pen(A(alpha, col), width))
                g.DrawArc(p, pole.X - rad, pole.Y - rad, rad * 2, rad * 2, start, sweep);
        }
        using (SolidBrush b = new SolidBrush(C(255, 255, 255))) g.FillEllipse(b, pole.X - 1.6f, pole.Y - 1.6f, 3.2f, 3.2f);
        // Mountains, three layers fading into the night.
        Color[] layers = { C(30, 34, 56), C(18, 20, 36), C(6, 7, 14) };
        float[] bases = { 380, 420, 470 };
        float[] amps = { 150, 120, 80 };
        for (int k = 0; k < 3; k++)
            using (SolidBrush b = new SolidBrush(layers[k])) g.FillPolygon(b, Ridge(11 + k * 5, bases[k], amps[k], 140 - 30 * k, 5));
        Text(g, "GR III", "Segoe UI", 13, FontStyle.Regular, A(150, C(220, 225, 240)), 636, 450, 4, false);
        return 0;
    }

    // ------------------------------------------------------------------ 2. film strip

    static int FilmStrip(Graphics g, Bitmap bmp)
    {
        Vertical(g, new RectangleF(0, 0, W, H), new[] { C(28, 24, 22), C(14, 12, 11) }, new[] { 0f, 1f });
        g.TranslateTransform(W / 2f, H / 2f);
        g.RotateTransform(-6);
        g.TranslateTransform(-W / 2f, -H / 2f);
        RectangleF strip = new RectangleF(-60, 130, W + 120, 220);
        using (SolidBrush b = new SolidBrush(C(190, 96, 38))) g.FillRectangle(b, strip);
        Vertical(g, new RectangleF(strip.X, strip.Y, strip.Width, 26), new[] { C(150, 70, 24), C(196, 100, 40) }, new[] { 0f, 1f });
        Vertical(g, new RectangleF(strip.X, strip.Bottom - 26, strip.Width, 26), new[] { C(196, 100, 40), C(150, 70, 24) }, new[] { 0f, 1f });
        for (float x = strip.X + 6; x < strip.Right; x += 25)
            using (GraphicsPath p = Rounded(new RectangleF(x, strip.Y + 7, 13, 12), 3))
            using (SolidBrush b = new SolidBrush(C(20, 17, 15)))
            {
                g.FillPath(b, p);
                using (Matrix m = new Matrix()) { m.Translate(0, strip.Height - 26); p.Transform(m); }
                g.FillPath(b, p);
            }
        // Frames: little scenes in the colours of some of the films.
        Color[][] scenes = {
            new[] { C(40, 98, 170), C(140, 190, 220), C(46, 110, 60) },
            new[] { C(232, 150, 70), C(250, 210, 140), C(70, 46, 40) },
            new[] { C(36, 102, 104), C(170, 210, 200), C(194, 60, 60) },
            new[] { C(20, 24, 40), C(90, 60, 110), C(240, 120, 50) },
            new[] { C(120, 110, 96), C(210, 200, 180), C(60, 56, 50) },
        };
        float fx = strip.X + 30;
        for (int k = 0; k < scenes.Length; k++, fx += 178)
        {
            RectangleF fr = new RectangleF(fx, strip.Y + 32, 160, strip.Height - 64);
            Vertical(g, fr, new[] { scenes[k][1], scenes[k][0] }, new[] { 0f, 1f });
            using (SolidBrush sun = new SolidBrush(A(220, C(255, 240, 210)))) g.FillEllipse(sun, fr.X + 100 - k * 12, fr.Y + 28 + k * 6, 26, 26);
            using (SolidBrush land = new SolidBrush(scenes[k][2]))
            {
                PointF[] hill = { new PointF(fr.X, fr.Bottom), new PointF(fr.X, fr.Y + 112), new PointF(fr.X + 50, fr.Y + 92 + k * 4), new PointF(fr.X + 104, fr.Y + 118), new PointF(fr.Right, fr.Y + 100), new PointF(fr.Right, fr.Bottom) };
                g.FillPolygon(land, hill);
            }
            using (Pen edge = new Pen(C(40, 26, 18), 2)) g.DrawRectangle(edge, fr.X, fr.Y, fr.Width, fr.Height);
            Text(g, (k + 21) + "", "Consolas", 12, FontStyle.Bold, C(255, 200, 120), fr.X + 4, strip.Bottom - 22, 0, false);
            Text(g, "▶" + (k + 21) + "A", "Consolas", 12, FontStyle.Bold, C(255, 200, 120), fr.X + 92, strip.Bottom - 22, 0, false);
        }
        Text(g, "GR FILM PACK  400", "Consolas", 12, FontStyle.Bold, C(255, 200, 120), strip.X + 120, strip.Y + 9, 2, false);
        Text(g, "GR FILM PACK  400", "Consolas", 12, FontStyle.Bold, C(255, 200, 120), strip.X + 560, strip.Y + 9, 2, false);
        g.ResetTransform();
        Text(g, "see you next roll", "Georgia", 22, FontStyle.Italic, A(200, C(236, 222, 200)), W / 2f, 420, 0, true);
        return 0;
    }

    static GraphicsPath Rounded(RectangleF r, float rad)
    {
        GraphicsPath p = new GraphicsPath();
        p.AddArc(r.X, r.Y, rad * 2, rad * 2, 180, 90);
        p.AddArc(r.Right - rad * 2, r.Y, rad * 2, rad * 2, 270, 90);
        p.AddArc(r.Right - rad * 2, r.Bottom - rad * 2, rad * 2, rad * 2, 0, 90);
        p.AddArc(r.X, r.Bottom - rad * 2, rad * 2, rad * 2, 90, 90);
        p.CloseFigure();
        return p;
    }

    // ------------------------------------------------------------------ 3. contours

    static int Contours(Graphics g, Bitmap bmp)
    {
        double[,] f = new double[W + 1, H + 1];
        for (int y = 0; y <= H; y++) for (int x = 0; x <= W; x++)
        {
            double dx = (x - 430) / 300.0, dy = (y - 220) / 260.0;
            f[x, y] = 0.75 * Fbm(x / 230.0, y / 230.0, 5, 4) + 0.35 * Math.Exp(-(dx * dx + dy * dy));
        }
        BitmapData d = bmp.LockBits(new Rectangle(0, 0, W, H), ImageLockMode.WriteOnly, bmp.PixelFormat);
        byte[] buf = new byte[d.Stride * H];
        const double levels = 26;
        for (int y = 0; y < H; y++) for (int x = 0; x < W; x++)
        {
            double v = f[x, y] * levels;
            double gx = (f[x + 1, y] - f[x, y]) * levels, gy = (f[x, y + 1] - f[x, y]) * levels;
            double grad = Math.Sqrt(gx * gx + gy * gy) + 1e-6;
            double frac = v - Math.Floor(v), dist = Math.Min(frac, 1 - frac) / grad;
            bool major = ((int)Math.Round(v)) % 5 == 0;
            double width = major ? 1.3 : 0.65;
            double ink = Math.Max(0, Math.Min(1, width + 0.5 - dist)) * (major ? 0.95 : 0.6);
            double t = Math.Min(1, f[x, y] * 1.1);
            double br = 14 + 18 * t, bg = 50 + 30 * t, bb = 60 + 26 * t;
            double cr = 236, cg = 222, cb = 190;
            int o = y * d.Stride + x * 3;
            buf[o + 2] = (byte)(br + (cr - br) * ink); buf[o + 1] = (byte)(bg + (cg - bg) * ink); buf[o] = (byte)(bb + (cb - bb) * ink);
        }
        Marshal.Copy(buf, 0, d.Scan0, buf.Length);
        bmp.UnlockBits(d);
        // The summit, marked.
        using (Pen p = new Pen(C(236, 120, 70), 2)) { g.DrawLine(p, 424, 214, 436, 226); g.DrawLine(p, 436, 214, 424, 226); }
        Text(g, "▲ 2351", "Consolas", 13, FontStyle.Regular, C(236, 222, 190), 444, 212, 0, false);
        using (SolidBrush b = new SolidBrush(C(14, 40, 48))) g.FillRectangle(b, 14, 440, 248, 28);
        Text(g, "CONTOUR INTERVAL 20 M", "Consolas", 11, FontStyle.Regular, A(170, C(236, 222, 190)), 24, 450, 2, false);
        return 0;
    }

    // ------------------------------------------------------------------ 4. aperture

    static int Aperture(Graphics g, Bitmap bmp)
    {
        using (LinearGradientBrush bg = new LinearGradientBrush(new Point(0, 0), new Point(W, H), C(24, 24, 28), C(6, 6, 8))) g.FillRectangle(bg, 0, 0, W, H);
        PointF c = new PointF(W / 2f, H / 2f);
        float R = 172;
        // Barrel rings.
        for (int i = 0; i < 6; i++)
            using (Pen p = new Pen(A(70 - i * 8, C(200, 200, 210)), 1)) g.DrawEllipse(p, c.X - R - 10 - i * 7, c.Y - R - 10 - i * 7, (R + 10 + i * 7) * 2, (R + 10 + i * 7) * 2);
        // The opening: bokeh through a nine-sided hole.
        int n = 9; float open = 78; float rot = 12;
        PointF[] hole = new PointF[n];
        for (int i = 0; i < n; i++) { double a = (rot + i * 360.0 / n) * Math.PI / 180; hole[i] = new PointF(c.X + open * (float)Math.Cos(a), c.Y + open * (float)Math.Sin(a)); }
        GraphicsPath hp = new GraphicsPath(); hp.AddPolygon(hole);
        g.SetClip(hp);
        Vertical(g, new RectangleF(c.X - open, c.Y - open, open * 2, open * 2), new[] { C(40, 30, 60), C(120, 50, 70), C(230, 130, 60) }, new[] { 0f, 0.6f, 1f });
        Random r = new Random(3);
        for (int i = 0; i < 26; i++)
        {
            float bx = c.X - open + (float)r.NextDouble() * open * 2, by = c.Y - open + (float)r.NextDouble() * open * 2, br = 10 + (float)r.NextDouble() * 22;
            Color bc = r.NextDouble() < 0.5 ? C(255, 190, 100) : C(255, 120, 140);
            using (SolidBrush b = new SolidBrush(A(70, bc))) g.FillEllipse(b, bx - br, by - br, br * 2, br * 2);
            using (Pen p = new Pen(A(110, bc), 1.2f)) g.DrawEllipse(p, bx - br, by - br, br * 2, br * 2);
        }
        g.ResetClip();
        // Blades: from each corner of the hole, a curved edge out to the rim.
        GraphicsPath rim = new GraphicsPath(); rim.AddEllipse(c.X - R, c.Y - R, R * 2, R * 2);
        g.SetClip(rim);
        for (int i = 0; i < n; i++)
        {
            PointF p0 = hole[i], p1 = hole[(i + 1) % n];
            double a = Math.Atan2(p0.Y - c.Y, p0.X - c.X) - 1.25;
            PointF far = new PointF(c.X + 2 * R * (float)Math.Cos(a), c.Y + 2 * R * (float)Math.Sin(a));
            double a1 = Math.Atan2(p1.Y - c.Y, p1.X - c.X) - 1.25;
            PointF far1 = new PointF(c.X + 2 * R * (float)Math.Cos(a1), c.Y + 2 * R * (float)Math.Sin(a1));
            int shade = 34 + (i * 7) % 22;
            using (GraphicsPath blade = new GraphicsPath())
            {
                blade.AddLine(p0, p1);
                blade.AddLine(p1, far1);
                blade.AddLine(far1, far);
                blade.CloseFigure();
                using (LinearGradientBrush b = new LinearGradientBrush(p0, far, C(shade + 30, shade + 30, shade + 36), C(shade - 20, shade - 20, shade - 16))) g.FillPath(b, blade);
            }
            using (Pen edge = new Pen(A(140, C(150, 150, 160)), 1.1f)) g.DrawLine(edge, p0, far);
        }
        g.ResetClip();
        using (Pen p = new Pen(C(90, 90, 98), 3)) g.DrawEllipse(p, c.X - R, c.Y - R, R * 2, R * 2);
        // Aperture scale around the barrel.
        string[] stops = { "2.8", "4", "5.6", "8", "11", "16" };
        for (int i = 0; i < stops.Length; i++)
        {
            double a = (-150 + i * 24) * Math.PI / 180;
            float tx = c.X + (R + 50) * (float)Math.Cos(a), ty = c.Y + (R + 50) * (float)Math.Sin(a);
            Text(g, stops[i], "Segoe UI", 15, FontStyle.Regular, i == 0 ? C(240, 160, 60) : C(170, 170, 180), tx, ty - 9, 0, true);
        }
        Text(g, "18.3 mm  F2.8", "Segoe UI", 13, FontStyle.Regular, C(150, 150, 160), W - 24 - 80, H - 30, 2, false);
        return 0;
    }

    // ------------------------------------------------------------------ 5. synthwave

    static int Synthwave(Graphics g, Bitmap bmp)
    {
        float horizon = 300;
        Vertical(g, new RectangleF(0, 0, W, horizon), new[] { C(18, 8, 44), C(70, 20, 90), C(200, 60, 110), C(255, 140, 90) }, new[] { 0f, 0.45f, 0.82f, 1f });
        // Sun with slits.
        RectangleF sun = new RectangleF(W / 2f - 120, horizon - 190, 240, 240);
        GraphicsPath sp = new GraphicsPath(); sp.AddEllipse(sun);
        Region clip = new Region(sp);
        for (int i = 0; i < 7; i++) { float y = horizon - 70 + i * 12; clip.Exclude(new RectangleF(0, y, W, 2 + i * 1.1f)); }
        g.SetClip(clip, CombineMode.Replace);
        Vertical(g, sun, new[] { C(255, 236, 120), C(255, 120, 90), C(240, 50, 130) }, new[] { 0f, 0.6f, 1f });
        g.ResetClip();
        // Mountains.
        using (SolidBrush b = new SolidBrush(C(40, 14, 70))) g.FillPolygon(b, Ridge(21, horizon + 2, 90, 120, 4));
        using (SolidBrush b = new SolidBrush(C(14, 6, 30))) g.FillRectangle(b, 0, horizon, W, H - horizon);
        // Perspective grid.
        using (Pen p = new Pen(A(220, C(255, 70, 190)), 1.6f))
        {
            for (int i = -14; i <= 14; i++) g.DrawLine(p, W / 2f + i * 26, horizon, W / 2f + i * 150, H + 10);
            for (int k = 0; k < 14; k++) { float y = horizon + (float)(Math.Pow(k / 13.0, 2.2) * (H - horizon)) + 3; g.DrawLine(p, 0, y, W, y); }
        }
        using (Pen glow = new Pen(A(120, C(255, 150, 210)), 3)) g.DrawLine(glow, 0, horizon, W, horizon);
        Text(g, "GOOD  NIGHT", "Segoe UI", 18, FontStyle.Bold, A(230, C(255, 220, 240)), W / 2f, 44, 6, true);
        return 0;
    }

    // ------------------------------------------------------------------ 6. bauhaus

    static int Bauhaus(Graphics g, Bitmap bmp)
    {
        Color cream = C(238, 228, 206), red = C(204, 62, 44), mustard = C(230, 170, 44), navy = C(30, 48, 92), ink = C(26, 24, 22), teal = C(48, 128, 120);
        using (SolidBrush b = new SolidBrush(cream)) g.FillRectangle(b, 0, 0, W, H);
        Action<Color, float, float, float, float, float, float> pie = (col, x, y, w, h, a, s) => { using (SolidBrush b = new SolidBrush(col)) g.FillPie(b, x, y, w, h, a, s); };
        Action<Color, float, float, float, float> rect = (col, x, y, w, h) => { using (SolidBrush b = new SolidBrush(col)) g.FillRectangle(b, x, y, w, h); };
        rect(navy, 0, 0, 240, 480);
        pie(mustard, 60, 60, 360, 360, 90, 180);
        rect(red, 240, 300, 240, 180);
        pie(cream, 240, 120, 360, 360, 180, 90);
        pie(teal, 480, 0, 240, 240, 0, 180);
        rect(ink, 480, 240, 240, 240);
        using (SolidBrush b = new SolidBrush(cream)) g.FillEllipse(b, 540, 300, 120, 120);
        using (SolidBrush b = new SolidBrush(red)) g.FillEllipse(b, 575, 335, 50, 50);
        using (Pen p = new Pen(ink, 6)) { g.DrawLine(p, 240, 0, 240, 480); g.DrawLine(p, 480, 0, 480, 240); g.DrawLine(p, 240, 300, 480, 300); }
        using (SolidBrush b = new SolidBrush(ink)) for (int i = 0; i < 6; i++) g.FillRectangle(b, 270 + i * 30, 40, 14, 14);
        Text(g, "GR", "Arial Black", 92, FontStyle.Regular, cream, 22, 290, 0, false);
        Text(g, "III", "Arial Black", 44, FontStyle.Regular, cream, 30, 398, 6, false);
        return 0;
    }

    // ------------------------------------------------------------------ 7. great wave

    static int GreatWave(Graphics g, Bitmap bmp)
    {
        Vertical(g, new RectangleF(0, 0, W, H), new[] { C(240, 226, 196), C(226, 206, 170) }, new[] { 0f, 1f });
        using (SolidBrush b = new SolidBrush(C(200, 58, 46))) g.FillEllipse(b, 520, 60, 110, 110);
        // A distant mountain.
        using (SolidBrush b = new SolidBrush(C(120, 132, 140))) g.FillPolygon(b, new[] { new PointF(330, 260), new PointF(410, 200), new PointF(428, 196), new PointF(446, 204), new PointF(540, 262) });
        using (SolidBrush b = new SolidBrush(C(244, 240, 230))) g.FillPolygon(b, new[] { new PointF(392, 214), new PointF(410, 200), new PointF(428, 196), new PointF(446, 204), new PointF(462, 216), new PointF(440, 212), new PointF(426, 220), new PointF(410, 212) });
        Color[] blues = { C(132, 170, 190), C(82, 128, 162), C(44, 86, 130), C(24, 56, 98), C(14, 34, 66) };
        Random r = new Random(9);
        for (int k = 0; k < blues.Length; k++)
        {
            float baseY = 250 + k * 50, amp = 16 + k * 9, len = 180 - k * 18;
            List<PointF> p = new List<PointF>();
            p.Add(new PointF(-4, H + 4));
            List<PointF> crest = new List<PointF>();
            for (int x = -4; x <= W + 4; x += 4)
            {
                double ph = x / len * 2 * Math.PI + k * 1.7;
                double s = Math.Sin(ph), shape = s > 0 ? Math.Pow(s, 0.6) : -Math.Pow(-s, 1.6);
                PointF q = new PointF(x, baseY - amp * (float)shape);
                p.Add(q);
                if (s > 0.55) crest.Add(q);
            }
            p.Add(new PointF(W + 4, H + 4));
            using (SolidBrush b = new SolidBrush(blues[k])) g.FillPolygon(b, p.ToArray());
            using (Pen line = new Pen(A(160, C(230, 236, 236)), 1.4f))
                for (int i = 1; i < p.Count - 2; i++)
                    if (Math.Abs(p[i].Y - p[i + 1].Y) < 6) g.DrawLine(line, p[i].X, p[i].Y + 7, p[i + 1].X, p[i + 1].Y + 7);
            using (SolidBrush foam = new SolidBrush(C(246, 244, 236)))
                foreach (PointF q in crest)
                    if (r.NextDouble() < 0.55) { float fr = 2 + (float)r.NextDouble() * (3 + k); g.FillEllipse(foam, q.X - fr, q.Y - fr - 2, fr * 2, fr * 2); }
        }
        Text(g, "おやすみ", "Yu Mincho", 26, FontStyle.Regular, C(200, 58, 46), 64, 52, 0, false);
        return 0;
    }

    // ------------------------------------------------------------------ 8. good night (the camera's own screen)

    static int GoodNight(Graphics g, Bitmap bmp)
    {
        using (SolidBrush b = new SolidBrush(C(8, 8, 9))) g.FillRectangle(b, 0, 0, W, H);
        Color white = C(236, 236, 232), dim = C(110, 110, 112), amber = C(255, 168, 40);
        // Exposure scale.
        float y = 300, x0 = 210, step = 50;
        using (Pen p = new Pen(dim, 2))
            for (int i = 0; i <= 18; i++) { float x = x0 + i * step / 3; float h = i % 3 == 0 ? 14 : 7; g.DrawLine(p, x, y - h, x, y); }
        string[] marks = { "-3", "-2", "-1", "0", "+1", "+2", "+3" };
        for (int i = 0; i < 7; i++) Text(g, marks[i], "Segoe UI", 13, FontStyle.Regular, i == 3 ? white : dim, x0 + i * step, y + 6, 0, true);
        using (SolidBrush b = new SolidBrush(amber)) g.FillPolygon(b, new[] { new PointF(x0 + 3 * step - 7, y - 30), new PointF(x0 + 3 * step + 7, y - 30), new PointF(x0 + 3 * step, y - 20) });
        Text(g, "GOOD NIGHT", "Segoe UI Light", 52, FontStyle.Regular, white, W / 2f, 150, 10, true);
        Text(g, "1/60   F2.8   ISO 200", "Consolas", 16, FontStyle.Regular, dim, W / 2f, 372, 3, true);
        // Battery, top right; frame counter, top left.
        using (Pen p = new Pen(white, 2)) g.DrawRectangle(p, 640, 30, 40, 18);
        using (SolidBrush b = new SolidBrush(white)) { g.FillRectangle(b, 681, 35, 4, 8); g.FillRectangle(b, 644, 34, 10, 10); }
        using (SolidBrush b = new SolidBrush(amber)) g.FillRectangle(b, 644, 34, 10, 10);
        Text(g, "[ 999 ]", "Consolas", 16, FontStyle.Regular, dim, 36, 30, 2, false);
        Text(g, "Zzz", "Segoe UI", 16, FontStyle.Italic, amber, 588, 30, 2, false);
        return 0;
    }
}
