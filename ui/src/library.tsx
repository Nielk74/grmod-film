// GR Mod's film library (GR III / IIIx films), their recipes, and the preview's sample photos.
import { useEffect, useMemo, useRef, useState } from 'react';
import { filmpack } from '@grmod/core';
import type { PresetResult, SlotId } from '@grmod/core';
import { FileButton, Ico, IconCanvas, Segmented, useDismiss } from './components';
import { engine } from './engine';
import { t } from './i18n';
import type { Key } from './i18n';
import { applySlot } from './preview';
import { SAMPLES } from './samples';
import { halationOf, loadPresetFile, previewPhoto, recipeOf, setHalation, setRecipe, setSample, useLibraryFilm, useStore } from './store';
import type { HaloColour, RecipeState } from './store';

const GROUPS: { id: filmpack.LookGroup; label: Key }[] = [
  { id: 'fujifilm', label: 'groupFujifilm' }, { id: 'stock', label: 'groupStock' }, { id: 'oppo', label: 'groupOppo' }, { id: 'creative', label: 'groupCreative' },
];

// ---------------------------------------------------------------- the films fitted once (thumbnails)
const fits = new Map<string, Promise<PresetResult>>();
/** A film of the library fitted to the camera's format (shared by every thumbnail; one at a time in the worker). */
function fitOf(look: filmpack.Look): Promise<PresetResult> {
  let f = fits.get(look.name);
  if (!f) { f = engine.convert('cube', filmpack.cubeText(look)); fits.set(look.name, f); f.catch(() => fits.delete(look.name)); }
  return f;
}

const THUMB_W = 192;
/** The preview photo, small: what the thumbnails render (changes with the photo). */
function useSmallPhoto(): ImageData | null {
  const rev = useStore((s) => s.photoRev);
  return useMemo(() => {
    const p = previewPhoto();
    if (!p) return null;
    const w = THUMB_W, h = Math.round((p.height / p.width) * THUMB_W);
    const src = document.createElement('canvas'); src.width = p.width; src.height = p.height; src.getContext('2d')!.putImageData(p, 0, 0);
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d', { willReadFrequently: true })!; g.imageSmoothingQuality = 'high'; g.drawImage(src, 0, 0, w, h);
    return g.getImageData(0, 0, w, h);
  }, [rev]); // eslint-disable-line react-hooks/exhaustive-deps
}

function Thumb({ look, photo }: { look: filmpack.Look; photo: ImageData | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let live = true;
    setReady(false);
    if (!photo) return;
    void fitOf(look).then((r) => {
      const c = ref.current;
      if (!live || !c) return;
      const out = applySlot(r.params, photo, true);
      c.width = out.width; c.height = out.height; c.getContext('2d')!.putImageData(out, 0, 0);
      setReady(true);
    }).catch(() => undefined);
    return () => { live = false; };
  }, [look, photo]);
  return <canvas ref={ref} className={`lib-thumb ${ready ? 'ready' : ''}`} style={{ aspectRatio: photo ? `${photo.width} / ${photo.height}` : '3 / 2' }} />;
}

/** The library as a dialog: pick a film for `slot`. */
export function LibraryDialog({ slot, onClose }: { slot: SlotId; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useDismiss(true, ref, onClose);
  const tile = useStore((s) => s.info?.tiles.film);
  const current = useStore((s) => s.slots[slot]?.preset?.library);
  const photo = useSmallPhoto();
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const icons = useMemo(() => (tile ? new Map(filmpack.LOOKS.map((l) => [l.name, filmpack.filmIcon(tile, l)])) : new Map<string, Uint8Array>()), [tile]);
  const pick = (name: string): void => { useLibraryFilm(slot, name); onClose(); };
  return (
    <div className="lib-backdrop">
      <div className="lib" ref={ref} role="dialog" aria-modal="true" aria-label={t('library')}>
        <header className="lib-head">
          <h2>{t('library')}</h2>
          <input className="input lib-search" value={query} placeholder={t('librarySearch')} spellCheck={false} autoFocus onChange={(e) => setQuery(e.target.value)} />
          <FileButton className="btn ghost" accept=".xmp,.cube" onFiles={(f) => { onClose(); void loadPresetFile(slot, f[0]); }}>{Ico.file}<span>{t('libraryImport')}</span></FileButton>
          <button className="btn ghost icon-only" aria-label={t('close')} title={t('close')} onClick={onClose}>{Ico.x}</button>
        </header>
        <div className="lib-body">
          {GROUPS.map((g) => {
            const looks = filmpack.LOOKS.filter((l) => l.group === g.id && (!q || l.name.toLowerCase().includes(q) || l.about.toLowerCase().includes(q)));
            if (!looks.length) return null;
            return (
              <section key={g.id} className="lib-group">
                <h3>{t(g.label)}</h3>
                <div className="lib-grid">
                  {looks.map((l) => (
                    <button key={l.name} className={`lib-card ${current === l.name ? 'on' : ''}`} onClick={() => pick(l.name)} title={l.about}>
                      <Thumb look={l} photo={photo} />
                      <span className="lib-meta">
                        {icons.get(l.name) && <IconCanvas pixels={icons.get(l.name)!} scale={1} />}
                        <span className="lib-text"><b className="ellipsis">{l.name}</b><span className="lib-about">{l.about}</span></span>
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- recipe
/** -4..+4 in steps of one, the value in the middle. */
function Stepper({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
  return (
    <span className="stepper" role="group" aria-label={label}>
      <button aria-label={`${label} −`} disabled={value <= -4} onClick={() => onChange(value - 1)}>−</button>
      <span className={`stepper-v ${value ? 'set' : ''}`}>{value > 0 ? `+${value}` : value}</span>
      <button aria-label={`${label} +`} disabled={value >= 4} onClick={() => onChange(value + 1)}>+</button>
    </span>
  );
}

const sign = (v: number): string => (v > 0 ? `+${v}` : `${v}`);
const GRAIN_LABEL: Key[] = ['grainOff', 'grainWeak', 'grainMedium', 'grainStrong'];
const HALO_LABEL: Key[] = ['haloOff', 'haloWeak', 'haloMedium', 'haloStrong'];

/** What a recipe holds, in one line (only what differs from neutral). */
function summary(r: RecipeState, halo: number, colour: HaloColour): string {
  const parts: string[] = [];
  if (r.grain.amount) parts.push(`${t('filmGrain')} ${t(GRAIN_LABEL[r.grain.amount])}${r.grain.size === 'large' ? ` · ${t('grainLarge')}` : ''}`);
  if (halo) parts.push(`${t('haloStart')} ${t(HALO_LABEL[halo])}${colour === 'red' ? '' : ` · ${t(({ white: 'haloWhite', gold: 'haloGold', orange: 'haloOrange' } as const)[colour])}`}`);
  if (r.sharpness) parts.push(`${t('recipeSharpness')} ${sign(r.sharpness)}`);
  if (r.clarity) parts.push(`${t('recipeClarity')} ${sign(r.clarity)}`);
  if (r.shading) parts.push(`${t('recipeShading')} ${sign(r.shading)}`);
  if (r.sky) parts.push(`${t('recipeSky')} ${sign(r.sky)}`);
  return parts.join('  ·  ');
}

/** A film's recipe: grain, where the camera's Halation, Sharpness, Clarity and Shading start. Folded to a line until opened. */
export function RecipeSection({ id }: { id: SlotId }) {
  const r = useStore((s) => recipeOf(id, s));
  const halo = useStore((s) => halationOf(id, s).preview);
  const colour = useStore((s) => halationOf(id, s).colour ?? 'red');
  const [open, setOpen] = useState(false);
  const line = summary(r, halo, colour);
  return (
    <div className={`recipe ${open ? 'open' : ''}`}>
      <button className="recipe-head" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="recipe-title">{t('recipe')}</span>
        <span className="recipe-sum ellipsis">{line || '—'}</span>
        <span className="recipe-chev">{Ico.right}</span>
      </button>
      {open && (
        <div className="recipe-body">
          <div className="recipe-row">
            <span>{t('filmGrain')}</span>
            <div className="chips">
              <Segmented value={String(r.grain.amount)} onChange={(v) => setRecipe(id, { grain: { ...r.grain, amount: Number(v) as 0 | 1 | 2 | 3 } })}
                options={GRAIN_LABEL.map((k, i) => ({ value: String(i), label: t(k) }))} />
              {r.grain.amount > 0 && <Segmented value={r.grain.size} onChange={(v) => setRecipe(id, { grain: { ...r.grain, size: v } })}
                options={[{ value: 'small', label: t('grainSmall') }, { value: 'large', label: t('grainLarge') }]} />}
            </div>
          </div>
          <div className="recipe-row">
            <span>{t('haloStart')}</span>
            <div className="chips">
              <Segmented value={String(halo)} onChange={(v) => setHalation(id, { preview: Number(v) as 0 | 1 | 2 | 3 })}
                options={HALO_LABEL.map((k, i) => ({ value: String(i), label: t(k) }))} />
              {halo > 0 && <Segmented value={colour} onChange={(v) => setHalation(id, { colour: v as HaloColour })}
                options={[{ value: 'red', label: t('haloRed') }, { value: 'orange', label: t('haloOrange') }, { value: 'gold', label: t('haloGold') }, { value: 'white', label: t('haloWhite') }]} />}
            </div>
          </div>
          <div className="recipe-row steppers">
            <label>{t('recipeSharpness')}<Stepper value={r.sharpness} label={t('recipeSharpness')} onChange={(v) => setRecipe(id, { sharpness: v })} /></label>
            <label>{t('recipeClarity')}<Stepper value={r.clarity} label={t('recipeClarity')} onChange={(v) => setRecipe(id, { clarity: v })} /></label>
            <label>{t('recipeShading')}<Stepper value={r.shading} label={t('recipeShading')} onChange={(v) => setRecipe(id, { shading: v })} /></label>
            <label title={t('recipeSkyHint')}>{t('recipeSky')}<Stepper value={r.sky} label={t('recipeSky')} onChange={(v) => setRecipe(id, { sky: v })} /></label>
          </div>
          <p className="small muted recipe-note">{t('recipeNote')} {t('recipePreviewNote')}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- samples
/** The sample photos as small buttons over the preview, and the user's own. */
export function SampleStrip() {
  const sample = useStore((s) => s.sample);
  const current = SAMPLES.find((x) => x.id === sample);
  return (
    <div className="samples">
      <div className="samples-row" role="radiogroup" aria-label={t('changePhoto')}>
        {SAMPLES.map((x) => (
          <button key={x.id} role="radio" aria-checked={x.id === sample} className={`sample ${x.id === sample ? 'on' : ''}`} title={t(x.label)} aria-label={t(x.label)}
            style={{ backgroundImage: `url(${x.url})` }} onClick={(e) => { e.stopPropagation(); setSample(x.id); }} />
        ))}
        <button role="radio" aria-checked={sample === 'own'} className={`sample own ${sample === 'own' ? 'on' : ''}`} title={t('sampleOwn')} aria-label={t('sampleOwn')}
          onClick={(e) => { e.stopPropagation(); setSample('own'); }}>{Ico.image}</button>
      </div>
      {current && <span className="sample-credit">{t('sampleCredit', { name: current.credit })}</span>}
    </div>
  );
}
