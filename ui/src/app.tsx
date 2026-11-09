import { LANGS } from '@grmod/core';
import type { CameraModel, FirmwareInfo, LangCode } from '@grmod/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Busy, ConfirmDialog, Hint, Ico, Select, Toasts, useDismiss } from './components';
import { host } from './host';
import { supportsBuildReceipt } from './build-receipt';
import { LANG_LABEL, UI_LANG, t } from './i18n';
import type { Key } from './i18n';
import { CopiesPage } from './copies';
import { BridgeBanner, BridgeDialog, FirmwareOnline, FirmwareRow, MODELS, modelLabel } from './firmware';
import { CropEditor, ImageControlPage, RatioPage, WallpaperPage } from './pages';
import { Tour, replayTour, restartTours } from './tour';
import { UpdatePill, UpdateWatcher, checkForUpdate, openWhatsNew } from './updates';
import {
  askForOfficial, bridgeLoaded, isGr3, backupCopies, extrasOn, copyList, deleteCopies, hasNameErrors, hasRatioErrors, ratioSpecs, revealBackups, writableCopy, writeCopy, menuPictures, outputFirmware, pendingChanges, refreshVolumes, selectVolume, setLang, setModel, setPage, setShowAll, useStore, wallReady,
} from './store';

const gb = (n: number): string => (n >= 1e9 ? `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`);

interface ResetGuideAccess {
  supported: boolean;
  expanded: boolean;
  open: (trigger: HTMLElement) => void;
}

function Sidebar({ guide }: { guide: ResetGuideAccess }) {
  const page = useStore((s) => s.page);
  const model = useStore((s) => s.model);
  const lang = useStore((s) => s.lang);
  const menuPics = useStore((s) => !!s.info?.capabilities.menuPictures);
  const info = useStore((s) => !!s.info);
  return (
    <aside className="sidebar">
      <nav>
        <button className={`nav ${page === 'ic' ? 'on' : ''}`} data-tour="nav-ic" onClick={() => setPage('ic')}>{Ico.aperture}<span>{t('navIC')}</span></button>
        <button className={`nav ${page === 'ratio' ? 'on' : ''}`} data-tour="nav-ratio" onClick={() => setPage('ratio')}>{Ico.ratio}<span>{t('navRatio')}</span></button>
        {(!isGr3(model) || menuPics || !info) && <button className={`nav ${page === 'wall' ? 'on' : ''}`} data-tour="nav-wall" onClick={() => setPage('wall')}>{Ico.image}<span>{t('navWall')}</span></button>}
      </nav>
      <div className="grow" />
      <button className={`nav low ${page === 'copies' ? 'on' : ''}`} data-tour="nav-copies" onClick={() => setPage('copies')}>{Ico.archive}<span>{t('navCopies')}</span></button>
      <div className="side-props">
        <FirmwareRow />
        <Select<CameraModel>
          variant="row" tour="model" label={t('model')} lead={<span className="side-label">{t('model')}</span>} value={model} onChange={setModel}
          options={MODELS.map((m) => ({ value: m, label: modelLabel(m) }))}
        />
        <Select<LangCode>
          variant="row" tour="language" label={t('language')} lead={<span className="side-label">{t('language')}</span>} value={lang} onChange={setLang}
          options={LANGS.map((l) => ({ value: l, label: LANG_LABEL[l] || l }))}
        />
      </div>
      <div className="side-foot">
        <button className="about-link" data-tour="version" title={t('wnTitle')} onClick={() => openWhatsNew()}>v{host.info?.version || ''}</button>
        <UpdatePill />
        <span className="grow" />
        <HelpMenu guide={guide} />
      </div>
    </aside>
  );
}

/** What the bottom bar offers on the copies page. */
function CopyActions() {
  const source = useStore((s) => s.copySource);
  const count = useStore((s) => copyList(s).length);
  const n = useStore((s) => s.copySel.length);
  const busy = useStore((s) => !!s.busy);
  const writable = useStore((s) => !!writableCopy(s) && s.volumes.some((v) => v.id === s.volumeId));
  const bridge = useStore((s) => bridgeLoaded(s));
  return (
    <div className="out-actions" data-tour="copies-actions">
      {source === 'pc' && <button className="btn" title={t('copiesOpenFolder')} onClick={() => revealBackups()}>{Ico.folder}<span className="out-label">{t('copiesOpenFolder')}</span></button>}
      <button className="btn" disabled={busy || count === 0} onClick={() => { void deleteCopies(true); }}>{t('copiesDeleteAll')}</button>
      <button className="btn danger" disabled={busy || n === 0} onClick={() => { void deleteCopies(false); }}>{Ico.trash}<span>{t('copiesDelete')}{n ? ` ${n}` : ''}</span></button>
      {source === 'card' && <button className="btn" disabled={busy || n === 0} onClick={() => { void backupCopies(); }}>{t('copiesBackup')}{n ? ` ${n}` : ''}</button>}
      <button className="btn primary" disabled={busy || (!writable && !bridge)} title={writable || bridge ? undefined : t('copiesPickOne')} onClick={() => { if (bridge) askForOfficial(); else void writeCopy(); }}>{t('writeCard')}</button>
    </div>
  );
}

function OutputBar({ guide }: { guide: ResetGuideAccess }) {
  const s = useStore((x) => x);
  const vol = s.volumes.find((v) => v.id === s.volumeId);
  // Image Control (with its switches), the added ratios and the power-off images go into one firmware file: every page writes the same thing.
  const isIC = s.page === 'ic' || s.page === 'ratio'; const isWall = s.page === 'wall';
  const can = !!s.info && s.info.models.includes(s.model) && (isIC ? s.info.capabilities.build : isWall ? (s.info.capabilities.wallpaper || s.info.capabilities.menuPictures) : s.info.capabilities.factoryEntry) && !s.busy && (isIC ? (pendingChanges(s).length + ratioSpecs(s).length > 0 || extrasOn(s) || (s.model !== 'MONO' && s.info.family !== 'gr3x' && s.extras.length > 0) || menuPictures(s).length > 0) && !hasNameErrors(s) && !hasRatioErrors(s) : isWall ? wallReady(s) && !hasNameErrors(s) && !hasRatioErrors(s) : true);
  const role: Key | '' = s.role === 'firmware' ? 'roleFirmware' : s.role === 'wallpaper' ? 'roleWallpaper' : s.role === 'mixed' ? 'roleMixed' : s.role === 'empty' ? 'roleEmpty' : '';
  // With the bridge firmware open the buttons stay live but offer the official download instead.
  const bridge = bridgeLoaded(s) && !s.busy;
  const run = (kind: 'card' | 'folder'): void => { if (bridge) { askForOfficial(); return; } void outputFirmware({ kind }); };
  return (
    <footer className="outbar">
      <div className="out-card" data-tour="card">
      <span className="out-ico">{Ico.card}</span>
      <Hint label={t('cardReqTitle')}>
        <b>{t('cardReqTitle')}</b>
        <span>{t('cardReq1')}</span>
      </Hint>
      <Select<string>
        variant="box" label={t('card')} value={vol?.id} placeholder={t('noCard')} onChange={selectVolume}
        options={s.volumes.map((v) => ({ value: v.id, label: `${v.id}${v.label && v.label !== v.id ? '  ' + v.label : ''}  ·  ${gb(v.total)}${v.fs && v.fs !== 'DEV' ? '  ·  ' + v.fs : ''}` }))}
        actions={[{ label: s.showAll ? t('showCardsOnly') : t('showAll'), run: () => setShowAll(!s.showAll) }]}
      />
      <button className="btn ghost icon-only" title={t('refresh')} aria-label={t('refresh')} onClick={() => { void refreshVolumes(); }}>{Ico.refresh}</button>
      </div>
      <div className="out-chips">
        {vol && role && <span className="chip">{t(role)}</span>}
      </div>
      <span className="grow" />
      {s.page === 'copies' && <CopyActions />}
      {s.page !== 'copies' && guide.supported && <button className="btn ghost reset-guide-link" aria-label={t('resetGuideOpen')} title={t('resetGuideOpen')} aria-controls="reset-guide-panel" aria-expanded={guide.expanded} onClick={(e) => guide.open(e.currentTarget)}>{Ico.help}<span className="out-label">{t('resetGuideOpen')}</span></button>}
      {s.page !== 'copies' && <button className="btn" data-tour="export" disabled={!can && !bridge} aria-label={t(supportsBuildReceipt(s.info, s.model) ? 'exportReceipt' : 'exportFolder')} title={t(supportsBuildReceipt(s.info, s.model) ? 'exportReceiptHint' : 'exportFolder')} onClick={() => run('folder')}>{Ico.folder}<span className="out-label">{t(supportsBuildReceipt(s.info, s.model) ? 'exportReceipt' : 'exportFolder')}</span></button>}
      {s.page !== 'copies' && <button className="btn primary" data-tour="write" disabled={!bridge && (!can || !vol)} onClick={() => run('card')}>{t('writeCard')}</button>}
    </footer>
  );
}

/** The ? button: this page's guide again (skippable), or every guide from the start as on first use. */
function HelpMenu({ guide }: { guide: ResetGuideAccess }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useDismiss(open, ref, () => setOpen(false));
  return (
    <div className="menu-wrap" ref={ref}>
      <button ref={trigger} className="help-btn" data-tour="help" title={t('tourHelp')} aria-label={t('tourHelp')} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{Ico.help}</button>
      {open && (
        <div className="menu up" role="menu">
          {guide.supported && <button role="menuitem" aria-controls="reset-guide-panel" aria-expanded={guide.expanded} onClick={() => { setOpen(false); if (trigger.current) guide.open(trigger.current); }}>{t('resetGuideOpen')}</button>}
          <button role="menuitem" onClick={() => { setOpen(false); replayTour(); }}>{t('tourReplay')}</button>
          <button role="menuitem" onClick={() => { setOpen(false); restartTours(); }}>{t('tourRestart')}</button>
          {host.available && <button role="menuitem" onClick={() => { setOpen(false); void checkForUpdate(false); }}>{t('updCheck')}</button>}
        </div>
      )}
    </div>
  );
}

/** Optional reading region: no backdrop, focus trap, or export action. */
function ResetGuide({ onClose }: { onClose: (restoreFocus: boolean) => void }) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const outside = (e: MouseEvent): void => { if (e.target instanceof Node && !panel.current?.contains(e.target)) onClose(false); };
    const escape = (e: KeyboardEvent): void => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose(true); } };
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('mousedown', outside); document.removeEventListener('keydown', escape); };
  }, [onClose]);
  return createPortal(
    <section id="reset-guide-panel" className="reset-guide-panel" ref={panel} role="region" aria-labelledby="reset-guide-title" lang={UI_LANG}>
      <div className="reset-guide-head">
        <h2 id="reset-guide-title">{t('resetGuideTitle')}</h2>
        <button ref={close} className="btn ghost icon-only" aria-label={t('resetGuideClose')} title={t('resetGuideClose')} onClick={() => onClose(true)}>{Ico.x}</button>
      </div>
      <div className="reset-guide-content" tabIndex={0} aria-label={t('resetGuideRead')}>
        <p><strong>{t('resetGuideScope')}</strong></p>
        <p>{t('resetGuideIntro')}</p>
        <ol>
          <li>{t('resetGuideStep1')}</li>
          <li>{t('resetGuideStep2')}</li>
          <li>{t('resetGuideStep3')}</li>
          <li><span lang="zh">设置 › 重设 › 恢复默认设置</span><p className="reset-guide-note">{t('resetGuideMenuTranslation')}</p></li>
          <li>{t('resetGuideStep5')}</li>
        </ol>
        <h3>{t('resetGuideCompatibility')}</h3>
        <p className="reset-guide-note">{t('resetGuideHistorical')}</p>
        <ul>
          <li>{t('resetGuideRecords')}</li>
          <li>{t('resetGuideTimestamp')}</li>
          <li>{t('resetGuidePresets')}</li>
          <li>{t('resetGuideNoFilm')}</li>
          <li>{t('resetGuideT6d')}</li>
        </ul>
        <h3>{t('resetGuideReturnTitle')}</h3>
        <p>{t('resetGuideReturn')}</p>
        <h3>{t('resetGuideIdentityTitle')}</h3>
        <p>{t('resetGuideIdentity')}</p>
        <p className="reset-guide-note">{t('resetGuideEvidence')}</p>
      </div>
    </section>, document.body,
  );
}

export function App() {
  const page = useStore((s) => s.page);
  const model = useStore((s) => s.model);
  const info = useStore((s) => s.info);
  const gr3 = isGr3(model);
  const menuPicsReady = useStore((s) => !!s.info?.capabilities.menuPictures);
  const fwOpen = useStore((s) => !!s.info);
  const ready = useStore((s) => s.ready);
  const supported = !!info && (model === 'GR3' || model === 'GR3_HDF') && info.models.includes(model) && info.family === 'gr3x' && info.version === '2.10' && info.filename === 'fwdc239b.bin' && !info.bridge;
  const [guideOwner, setGuideOwner] = useState<{ info: FirmwareInfo; model: CameraModel } | null>(null);
  const guideTrigger = useRef<HTMLElement | null>(null);
  const guideOpen = supported && guideOwner?.info === info && guideOwner.model === model;
  const closeGuide = useCallback((restoreFocus: boolean): void => {
    setGuideOwner(null);
    if (restoreFocus && guideTrigger.current?.isConnected) guideTrigger.current.focus();
  }, []);
  const openGuide = (trigger: HTMLElement): void => {
    if (supported && info) { guideTrigger.current = trigger; setGuideOwner({ info, model }); }
  };
  useEffect(() => { if (guideOwner && !guideOpen) setGuideOwner(null); }, [guideOwner, guideOpen]);
  const guide: ResetGuideAccess = { supported, expanded: guideOpen, open: openGuide };
  if (!host.available) return <div className="nohost">{t('hostMissing')}</div>;
  return (
    <div className="app" onDragOver={(e) => { if (e.dataTransfer.types.includes('Files')) e.preventDefault(); }} onDrop={(e) => e.preventDefault()}>
      <Sidebar guide={guide} />
      <main className="main">
        <BridgeBanner />
        <div className="stage">{ready ? (page === 'ratio' ? <RatioPage /> : page === 'wall' && (!gr3 || menuPicsReady || !fwOpen) ? <WallpaperPage /> : page === 'copies' ? <CopiesPage /> : <ImageControlPage />) : <div className="page"><span className="spinner" /></div>}</div>
        <OutputBar guide={guide} />
      </main>
      {guideOpen && <ResetGuide onClose={closeGuide} />}
      <CropEditor />
      <FirmwareOnline />
      <BridgeDialog />
      <UpdateWatcher />
      <ConfirmDialog />
      <Tour />
      <Busy />
      <Toasts />
    </div>
  );
}
