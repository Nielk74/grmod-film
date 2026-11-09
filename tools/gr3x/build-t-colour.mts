// SPDX-License-Identifier: GPL-2.0-only
/** Standalone GR III 2.10 data-only multi-axis diagnostic. No device I/O.
 * Run with vite-node; --self-test exercises the bounded probe codec.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { Engine } from '../../core/src/app/engine';
import { Firmware, sectionsOf, buildGrown, FRAME_SIZE, sum32 } from '../../core/src/fw/container';
import { selfCheckGrown } from '../../core/src/fw/selfcheck';
import { GR3_210, GR3X_160 } from '../../core/src/fw/gr3x/profile';
import { readGr3xLookRecipe } from '../../core/src/fw/gr3x/look-recipe';
import { readGr3xBuildRecipe } from '../../core/src/fw/gr3x/ratio-recipe';
import { buildGr3xTestFirmware } from '../../core/src/fw/gr3x/research-package';
import { planGr3xMenu } from '../../core/src/fw/gr3x/geometry';
import { readRes, resFile } from '../../core/src/fw/aspect/res';
import { gr3xPicturePath } from '../../core/src/fw/gr3x/shutdown';
import { HALATION } from '../../core/src/fw/aspect/halation';
import { quantizeSlot } from '../../core/src/color/camera';
import { movWord } from '../../core/src/fw/aspect/arm';
import type { Gr3xFilmLook, Gr3xLookOptions } from '../../core/src/fw/gr3x/image-control';
import type { Range } from '../../core/src/fw/types';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const CURRENT = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55';
const CODEC = '0c15c8f9a97b464ac23ab1641740a8263e0068b0';
const REFERENCES = '49ac27de2266575936c6f562901ed1b784c9d5f74d577fd1e93bd36e242b2c97';
const PINS: Record<string, string> = {
  'v3-portra-400': '890bcdf75029951d3fb3de19fcb24300f4e22ec93061a2c07c7f1b1b378e9197',
  'v3-cinestill-800t': '249ed05a44826b00415d5555dc7160c211ec4295193209ae9409fe8fab730948',
  'v3-gold-200': '6caa69980013cd07992ed4fa2c775ca143d509350b43458cdf6ffe6a1d682894',
  'gold-plus2-approved': '91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6',
};
const MA_RECORD = 0x53dc2ba0, MA_BLOCK = 0x53dc31d0, BLOCK_BYTES = 2160;
const BLOCK_HASH = '383996f239137d4678c676deaf0d4201be62aca8699deed1e6b987f8b52a1564';
const MAGIC = Buffer.from('GR3-TCOLOUR-1\0', 'ascii');
const LABELS = ['control', 'all', 'bit0', 'bit1', 'bit2', 'bit3', 'bit4', 'bit5', 'x0.50', 'x0.75', 'x1.25', 'group0x2', 'adjacentPQ', 'adjacentQP'];
const RETAIN = ['Portra 400', 'CineStill 800T', 'Gold 200', 'Gold +2 EV (approved)', 'Kodachrome 64', 'Astia'];
const h = HALATION as unknown as { start: number; narrow: number; wide: number; mix: number; gain: number[] };
const shippedGains = [...h.gain];
const sha = (b: Uint8Array | string) => createHash('sha256').update(b).digest('hex');
const same = (a: Uint8Array, b: Uint8Array) => Buffer.from(a).equals(Buffer.from(b));
function need(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
function historicalProfile() {
  h.start = 228; h.narrow = .006; h.wide = .035; h.mix = .3;
  h.gain = shippedGains.map(g => +(g * .78).toFixed(2));
  return { start: h.start, narrow: h.narrow, wide: h.wide, mix: h.mix, gain: [...h.gain] };
}
function diagnosticProfile() { historicalProfile(); h.gain = [0, 0, 0]; return { ...historicalProfileValues(), gain: [0, 0, 0] }; }
function historicalProfileValues() { return { start: h.start, narrow: h.narrow, wide: h.wide, mix: h.mix }; }
function payload(film: Gr3xFilmLook) {
  const p = film.preset; need(p, `Missing quantized preset: ${film.name}`);
  const values = [...Array.from(p.matrixQ13), ...p.curves.flatMap(c => Array.from(c)), ...Array.from(p.postQ9 ?? [])];
  const bytes = Buffer.alloc(values.length * 2); values.forEach((v, i) => bytes.writeUInt16LE(v & 65535, 2 * i));
  return sha(bytes);
}
function recipes(raw: Uint8Array) {
  const decoded = new Firmware(raw).decoded, rt = sectionsOf(decoded).find(s => s.name === 'RTOS');
  need(rt && rt.size > GR3X_160.rtosLength, 'Missing extended RTOS');
  const appended = decoded.subarray(rt.offset + GR3X_160.rtosLength, rt.offset + rt.size);
  const looks = readGr3xLookRecipe(appended), features = readGr3xBuildRecipe(appended);
  need(looks && features, 'Missing self-describing base recipes');
  return { decoded, rt, looks, features };
}
function vaOffset(decoded: Uint8Array, address: number, size: number) {
  const rt = sectionsOf(decoded).find(s => s.name === 'RTOS'); need(rt, 'Missing RTOS');
  const p = GR3_210;
  const rom = address >= p.ramBase && address + size <= p.ramBase + p.ramLength ? p.ramSource + address - p.ramBase : address;
  const relative = rom - p.rtosBase;
  need(Number.isSafeInteger(relative) && size >= 0 && relative >= 0 && relative + size <= rt.size, `VA outside RTOS: ${address.toString(16)}`);
  return rt.offset + relative;
}
function readVA(decoded: Uint8Array, address: number, size: number) { const at = vaOffset(decoded, address, size); return decoded.slice(at, at + size); }
function wordVA(decoded: Uint8Array, address: number) { const b = readVA(decoded, address, 4); return new DataView(b.buffer).getUint32(0, true); }
function sourceSnapshot() {
  const names = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '--', 'core/src', 'tools/gr3x/build-t-colour.mts', 'tools/gr3x/package_probe.py', 'tools/gr3x/identity.py', 'tools/gr3x/ratio_menu.py', 'tools/gr3x/loader_probe.py'], { cwd: ROOT, encoding: 'utf8' }).trim().split(/\r?\n/).filter(Boolean);
  return [...new Set(names)].sort().map(path => ({ path, sha256Lf: sha(readFileSync(join(ROOT, path), 'utf8').replace(/\r\n/g, '\n')) }));
}

function probeBlocks(standard: readonly number[]): number[][] {
  need(standard.length === 540, 'Standard must have 540 source coefficients');
  need(standard.every(v => Number.isInteger(v) && v >= -2048 && v <= 2047), 'Invalid source coefficient');
  const mix = (g: number, reverse = false) => {
    const s = g ? 1024 : 512, a = s * 3 / 4, b = s / 4;
    return reverse ? [a, 0, b, b, a, 0, 0, b, a] : [a, b, 0, 0, a, b, b, 0, a];
  };
  const apply = (fn: (g: number) => number[] | undefined) => Array.from({ length: 60 }, (_, g) => fn(g) ?? standard.slice(g * 9, g * 9 + 9)).flat();
  const scale = (numerator: number) => Array.from({ length: 180 }, (_, row) => {
    const input = standard.slice(row * 3, row * 3 + 3), raw = input.map(v => v * numerator);
    const out = raw.map(v => Math.floor(v / 4));
    let remainder = Math.round(input.reduce((a, b) => a + b) * numerator / 4) - out.reduce((a, b) => a + b);
    const order = [0, 1, 2].sort((a, b) => (raw[b] - out[b] * 4) - (raw[a] - out[a] * 4) || a - b);
    for (const index of order) if (remainder-- > 0) out[index]++;
    return out;
  }).flat();
  const blocks = [[...standard], apply(g => mix(g)), ...Array.from({ length: 6 }, (_, bit) => apply(g => ((g >> bit) & 1) ? mix(g) : undefined)),
    scale(2), scale(3), scale(5), apply(g => g ? undefined : standard.slice(0, 9).map(v => v * 2)),
    apply(g => g >= 25 && g < 35 ? mix(g, g >= 30) : undefined), apply(g => g >= 25 && g < 35 ? mix(g, g < 30) : undefined)];
  need(blocks.every(b => b.length === 540 && b.every(v => Number.isInteger(v) && v >= -2048 && v <= 2047)), 'Probe coefficient exceeds native signed 12-bit range');
  return blocks;
}

interface Probe { letter: string; id: number; name: string; block: number; array: number; record: number; coefficients: number[]; sourceBlockSha256: string }
interface Diagnostic {
  schema: 1; kind: 'GR3-TCOLOUR-1'; officialSha256: string; baseSha256: string; baseDecodedSha256: string;
  table: number; extensionAddress: number; dataBytes: number; probes: Probe[];
  nativeRecordWords: number[]; coefficientFormat: string; semanticLimit: string;
}
function i32Bytes(values: readonly number[]) { const b = Buffer.alloc(values.length * 4); values.forEach((v, i) => b.writeInt32LE(v, i * 4)); return b; }
function u32Bytes(values: readonly number[]) { const b = Buffer.alloc(values.length * 4); values.forEach((v, i) => b.writeUInt32LE(v >>> 0, i * 4)); return b; }
function descriptor(base: Uint8Array, decoded: Uint8Array, table: number, original: Uint8Array): Diagnostic {
  const { rt } = recipes(base), extensionAddress = GR3_210.rtosBase + rt.size;
  const standardBytes = readVA(original, MA_BLOCK, BLOCK_BYTES); need(sha(standardBytes) === BLOCK_HASH, 'Factory multi-axis source block mismatch');
  const standard = Array.from({ length: 540 }, (_, i) => new DataView(standardBytes.buffer).getInt32(i * 4, true));
  const recordBytes = readVA(original, MA_RECORD, 24), nativeRecordWords = Array.from({ length: 6 }, (_, i) => new DataView(recordBytes.buffer).getUint32(i * 4, true));
  need(JSON.stringify(nativeRecordWords) === JSON.stringify([0x53dc3198, 0x53dc2bb8, 0x55019828, 0x55019848, 0x53dc2bcc, 0x53dc3a40]), 'Factory multi-axis record changed');
  let used = 0;
  const probes = probeBlocks(standard).map((coefficients, k): Probe => {
    const block = extensionAddress + used; used += BLOCK_BYTES;
    const array = extensionAddress + used; used += 32;
    const record = extensionAddress + used; used += 24;
    return { letter: String.fromCharCode(65 + k), id: 70 + k, name: `MA ${String.fromCharCode(65 + k)} ${LABELS[k]}`, block, array, record, coefficients, sourceBlockSha256: sha(i32Bytes(coefficients)) };
  });
  return { schema: 1, kind: 'GR3-TCOLOUR-1', officialSha256: GR3_210.sha256, baseSha256: sha(base), baseDecodedSha256: sha(decoded), table, extensionAddress,
    dataBytes: used, probes, nativeRecordWords, coefficientFormat: '540 signed little-endian int32 Q10 values; native packer uses low signed 12 bits',
    semanticLimit: 'Group indices and adjacent-index patterns are hypotheses; selection/packing does not prove pixel activity, sector geometry or pipeline order.' };
}
function applyDiagnostic(base: Uint8Array, d: Diagnostic, recipeBytes: Uint8Array) {
  const fw = new Firmware(base), old = fw.decoded, rt = sectionsOf(old).find(s => s.name === 'RTOS'); need(rt, 'Missing base RTOS');
  need(d.schema === 1 && d.kind === 'GR3-TCOLOUR-1' && d.baseSha256 === sha(base) && d.baseDecodedSha256 === sha(old), 'Diagnostic/base identity mismatch');
  need(d.probes.length === 14 && d.dataBytes === 14 * (2160 + 32 + 24), 'Invalid diagnostic allocation');
  need(d.extensionAddress === GR3_210.rtosBase + rt.size, 'Diagnostic extension is not at RTOS end');
  need(wordVA(old, 0x536dc290) === movWord(12, d.table & 65535) && wordVA(old, 0x536dc298) === movWord(12, d.table >>> 16, true), 'Descriptor/table pointer mismatch');
  need(wordVA(old, 0x536dc2b0) === 0xe79cc101, 'Native multi-axis selector changed');
  need(JSON.stringify(d.nativeRecordWords) === JSON.stringify([0x53dc3198, 0x53dc2bb8, 0x55019828, 0x55019848, 0x53dc2bcc, 0x53dc3a40]), 'Ancillary record fields changed');
  need(same(Buffer.from(JSON.stringify(d) + '\n', 'utf8'), recipeBytes), 'Noncanonical diagnostic recipe bytes');
  const growth = Math.ceil((d.dataBytes + MAGIC.length + 4 + recipeBytes.length + 4) / FRAME_SIZE) * FRAME_SIZE;
  need(rt.size + growth <= 0x4000000 && GR3_210.rtosBase + rt.size + growth < GR3_210.ramBase, 'RTOS diagnostic extension exceeds bounds');
  const end = rt.offset + rt.size, out = new Uint8Array(old.length + growth);
  out.set(old.subarray(0, end)); out.set(old.subarray(end), end + growth);
  const view = new DataView(out.buffer), ranges: Range[] = [{ what: 'T-colour RTOS section length', offset: rt.offset - 4, length: 4 }, { what: 'T-colour data-only extension and checksum', offset: end, length: growth }];
  view.setUint32(rt.offset - 4, rt.size + growth, true);
  for (const [k, p] of d.probes.entries()) {
    need(p.id === 70 + k && p.letter === String.fromCharCode(65 + k) && p.coefficients.length === 540 && p.coefficients.every(v => Number.isInteger(v) && v >= -2048 && v <= 2047), 'Invalid diagnostic probe');
    need(p.block === d.extensionAddress + k * (2160 + 32 + 24) && p.array === p.block + 2160 && p.record === p.array + 32, 'Probe allocation overlap');
    need(sha(i32Bytes(p.coefficients)) === p.sourceBlockSha256, 'Coefficient block hash mismatch');
    const record = [...d.nativeRecordWords]; record[2] = p.array;
    out.set(i32Bytes(p.coefficients), end + p.block - d.extensionAddress);
    out.set(u32Bytes(Array(8).fill(p.block)), end + p.array - d.extensionAddress);
    out.set(u32Bytes(record), end + p.record - d.extensionAddress);
    const cell = vaOffset(old, d.table + p.id * 4, 4); need(view.getUint32(cell, true) === MA_RECORD, 'Probe table cell was not Standard');
    view.setUint32(cell, p.record, true); ranges.push({ what: `T-colour ${p.letter} table cell only`, offset: cell, length: 4 });
  }
  let at = end + d.dataBytes; out.set(MAGIC, at); at += MAGIC.length;
  view.setUint32(at, recipeBytes.length, true); at += 4; out.set(recipeBytes, at);
  view.setUint32(end + growth - 4, (-sum32(out)) >>> 0, true); need(sum32(out) === 0, 'Diagnostic decoded checksum failed');
  const built = buildGrown(fw, out, [{ at: end, length: growth }]);
  const checks = selfCheckGrown(base, built.out, ranges, out); need(Object.values(checks).every(v => v === true), `Diagnostic container checks failed: ${JSON.stringify(checks)}`);
  return { bytes: built.out, decoded: out, growth, ranges, checks, recipeOffset: end + d.dataBytes, recipeBytes: recipeBytes.length };
}

// Independent decoder and patch reconstruction. No firmware operations or REA session.
// The only native execution below is the existing updater/loader regression, whose I/O is stubbed.
const INDEPENDENT = String.raw`
import hashlib,json,struct,sys
from pathlib import Path
root,codec,official_path,out_path,persist=sys.argv[1:]
out=Path(out_path);sys.path.insert(0,codec);sys.path.insert(0,str(Path(root)/'tools/gr3x'))
from gr4_editor.codec.container import inspect_container,sum32
from gr4_editor.codec.frames import decode_payload,section_rows
from identity import by_container
def sha(b):return hashlib.sha256(b).hexdigest()
def load(name):return (out/name).read_bytes()
official=Path(official_path).read_bytes();base=load('BASE-VERIFIED.bin');candidate=load('UNVALIDATED.bin')
recipe=load('diagnostic-recipe.json');d=json.loads(recipe);report=json.loads(load('diagnostic-manifest.json'))
profile=by_container(official)
# Run the ordinary base checker on every verification, including repeat invocations.
# Its CLI uses exclusive report creation; the function API avoids a stale-report shortcut.
from package_probe import verify as package_verify
base_package=package_verify(official,base,json.loads(load('base-patch-manifest.json')),json.loads(load('base-build-report.json')),Path(codec))
if persist=='persist':(out/'base-independent-verification.json').write_text(json.dumps(base_package,indent=2)+'\n',encoding='utf-8')
def decode(raw):
 info=inspect_container(raw)
 assert info['additive_sum32']==0 and info['metadata_length']==0
 decoded,frames=decode_payload(raw[128:info['payload_end']],info['decoded_size'])
 assert sum32(decoded)==0 and len(decoded)==info['decoded_size']
 assert sum(f.decoded_end-f.decoded_start for f in frames)==len(decoded)
 return info,decoded,section_rows(decoded)
oi,original,os=decode(official);bi,old,bs=decode(base);ci,dec,cs=decode(candidate)
assert profile['container_sha256']==d['officialSha256'] and sha(base)==d['baseSha256'] and sha(old)==d['baseDecodedSha256']
assert sha(candidate)==report['candidate']['sha256'] and sha(dec)==report['candidate']['decodedSha256']
assert official[:128]==base[:128]==candidate[:128] and oi['project']==bi['project']==ci['project']==588
def model_area(raw,info):return raw[(info['payload_end']+3)&~3:len(raw)-24]
assert model_area(official,oi)==model_area(base,bi)==model_area(candidate,ci)
assert [s['name'] for s in os]==[s['name'] for s in bs]==[s['name'] for s in cs]
brt=next(s for s in bs if s['name']=='RTOS');crt=next(s for s in cs if s['name']=='RTOS');ort=next(s for s in os if s['name']=='RTOS')
rt_start=brt['start']+16;rt_end=brt['end'];rt_size=rt_end-rt_start;growth=crt['end']-(crt['start']+16)-rt_size
assert crt['start']==brt['start'] and growth>0 and growth%0x6000==0
assert len(dec)==len(old)+growth and rt_size+growth<=0x4000000 and 0x53000000+rt_size+growth<0x55000000
def off(va):
 if 0x55000000<=va<0x5503a080:va=0x5407b540+va-0x55000000
 v=rt_start+va-0x53000000
 assert rt_start<=v and v+4<=rt_end
 return v
def original_va(va,n):
 if 0x55000000<=va<0x5503a080:va=0x5407b540+va-0x55000000
 p=ort['start']+16+va-0x53000000
 assert ort['start']+16<=p and p+n<=ort['end']
 return original[p:p+n]
def word(va):return struct.unpack_from('<I',old,off(va))[0]
table=d['table'];mov=lambda value,top:(0xe340c000 if top else 0xe300c000)|((value&0xf000)<<4)|(value&0xfff)
assert word(0x536dc290)==mov(table&65535,False) and word(0x536dc298)==mov(table>>16,True) and word(0x536dc2b0)==0xe79cc101
factory=original_va(0x53dc31d0,2160)
assert sha(factory)=='383996f239137d4678c676deaf0d4201be62aca8699deed1e6b987f8b52a1564'
standard=list(struct.unpack('<540i',factory));record=list(struct.unpack('<6I',original_va(0x53dc2ba0,24)))
assert record==d['nativeRecordWords']==[0x53dc3198,0x53dc2bb8,0x55019828,0x55019848,0x53dc2bcc,0x53dc3a40]
def mixing(g,reverse=False):
 s=1024 if g else 512;a=3*s//4;b=s//4
 return [a,0,b,b,a,0,0,b,a] if reverse else [a,b,0,0,a,b,b,0,a]
def scaled(num):
 result=[]
 for row in range(180):
  vals=standard[row*3:row*3+3];raw=[x*num for x in vals];q=[x//4 for x in raw]
  n=sum(vals)*num//4-sum(q)
  order=sorted(range(3),key=lambda j:(-(raw[j]-q[j]*4),j))
  for j in order[:n]:q[j]+=1
  result+=q
 return result
def block(k):
 if k==0:return standard[:]
 if k in (8,9,10):return scaled({8:2,9:3,10:5}[k])
 result=[]
 for g in range(60):
  vals=standard[g*9:g*9+9]
  if k==1 or 2<=k<=7 and ((g>>(k-2))&1):vals=mixing(g)
  elif k==11 and g==0:vals=[x*2 for x in vals]
  elif k in (12,13) and 25<=g<35:vals=mixing(g,(g>=30) if k==12 else (g<30))
  result+=vals
 return result
assert d['schema']==1 and d['kind']=='GR3-TCOLOUR-1' and len(d['probes'])==14
assert d['extensionAddress']==0x53000000+rt_size and d['dataBytes']==14*2216
expected=bytearray(old[:rt_end]+bytes(growth)+old[rt_end:])
struct.pack_into('<I',expected,rt_start-4,rt_size+growth)
cell_ranges=[]
for k,p in enumerate(d['probes']):
 assert p['id']==70+k and p['letter']==chr(65+k)
 b=d['extensionAddress']+k*2216;a=b+2160;r=a+32
 assert (p['block'],p['array'],p['record'])==(b,a,r)
 values=block(k);assert p['coefficients']==values and all(-2048<=x<=2047 for x in values)
 binary=struct.pack('<540i',*values);assert sha(binary)==p['sourceBlockSha256']
 record_copy=record[:];record_copy[2]=a
 pos=rt_end+k*2216
 expected[pos:pos+2160]=binary;expected[pos+2160:pos+2192]=struct.pack('<8I',*([b]*8));expected[pos+2192:pos+2216]=struct.pack('<6I',*record_copy)
 cell=off(table+p['id']*4);assert struct.unpack_from('<I',old,cell)[0]==0x53dc2ba0
 struct.pack_into('<I',expected,cell,r);cell_ranges.append((cell,4))
magic=b'GR3-TCOLOUR-1\0';pos=rt_end+d['dataBytes']
assert pos+len(magic)+4+len(recipe)<=rt_end+growth-4
expected[pos:pos+len(magic)]=magic;struct.pack_into('<I',expected,pos+len(magic),len(recipe))
expected[pos+len(magic)+4:pos+len(magic)+4+len(recipe)]=recipe
struct.pack_into('<I',expected,rt_end+growth-4,(-sum32(expected))&0xffffffff)
assert bytes(expected)==dec,'Candidate differs from independently reconstructed exact whitelist'
recovered=bytearray(dec[:rt_end]+dec[rt_end+growth:]);struct.pack_into('<I',recovered,rt_start-4,rt_size)
for cell,_ in cell_ranges:recovered[cell:cell+4]=old[cell:cell+4]
assert bytes(recovered)==old and sha(recovered)==d['baseDecodedSha256']
for a,b in zip(bs,cs):
 assert a['name']==b['name'] and a['flags']==b['flags']
 if a['name']!='RTOS':assert old[a['start']:a['end']]==dec[b['start']:b['end']]
icon=next(s for s in cs if s['name']=='ICONBIN');assert icon['end']-icon['start']-16<=0x1800000-0x40000
assert sha(original[ort['start']+16:ort['end']])==profile['rtos_sha256']
# Existing bounded loader probe: version acceptance, partition lengths and BOOT requests. Disk writes stubbed.
from loader_probe import verify as loader
boot=next(s for s in os if s['name']=='BOOT')
loader_report=loader(original[ort['start']+16:ort['end']],original[boot['start']+16:boot['end']],official,candidate,{'inputSha256':sha(official),'outputSha256':sha(candidate),'rtosGrowth':crt['end']-crt['start']-(ort['end']-ort['start'])})
result={'schema':1,'decoderCommit':'0c15c8f9a97b464ac23ab1641740a8263e0068b0','candidateSha256':sha(candidate),'decodedSha256':sha(dec),'baseSha256':sha(base),'independentExactReconstruction':True,'reverseBaseExact':True,'probeFormulaVerification':True,'modelUpdaterHeaderPreserved':True,'zeroChecksums':True,'onlyRtosGrowthVersusBase':growth,'nonRtosSectionsIdenticalToBase':True,'loader':loader_report,'hardwareTested':False,'cameraIoPerformed':False}
if persist=='persist':(out/'independent-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
`;

function checkCodec(codec: string) {
  need(resolve(execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd: codec, encoding: 'utf8' }).trim()).toLowerCase() === codec.toLowerCase(), 'Codec must be its own checkout');
  need(execFileSync('git', ['rev-parse', 'HEAD'], { cwd: codec, encoding: 'utf8' }).trim() === CODEC, 'Independent codec commit mismatch');
  need(!execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: codec, encoding: 'utf8' }).trim(), 'Independent codec tracked files are modified');
}
function writeJson(out: string, name: string, data: unknown) { writeFileSync(join(out, name), JSON.stringify(data, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' }); }
function readJson<T>(path: string): T { return JSON.parse(readFileSync(path, 'utf8')) as T; }
function runPython(python: string, args: string[]) {
  try { return execFileSync(python, args, { cwd: ROOT, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] }); }
  catch (error) { const e = error as { stdout?: string; stderr?: string }; throw new Error(`Python verification failed:\n${e.stdout ?? ''}\n${e.stderr ?? ''}`, { cause: error }); }
}
async function verifyOutput(officialPath: string, out: string, python: string, codec: string, persist = false) {
  checkCodec(codec);
  const official = new Uint8Array(readFileSync(officialPath)); need(sha(official) === GR3_210.sha256, 'Official SHA-256 mismatch');
  diagnosticProfile();
  const base = new Uint8Array(readFileSync(join(out, 'BASE-VERIFIED.bin'))), candidate = new Uint8Array(readFileSync(join(out, 'UNVALIDATED.bin')));
  const recipeBytes = readFileSync(join(out, 'diagnostic-recipe.json')), d = JSON.parse(recipeBytes.toString('utf8')) as Diagnostic;
  const baseSummary = await (await Engine.open(official)).inspect(base); need(baseSummary.verified && baseSummary.slots.length === 20, 'Fresh Engine base verification failed');
  const rebuilt = applyDiagnostic(base, d, recipeBytes); need(same(rebuilt.bytes, candidate), 'Deterministic diagnostic reapply does not match candidate');
  const candidateSummary = await (await Engine.open(official)).inspect(candidate);
  need(candidateSummary.kind === 'unknown' && !candidateSummary.verified, 'Diagnostic must remain rejected by the general app write path');
  // Undo table edits, RTOS size and the extension, then compare EVERY decoded byte of the verified base.
  const old = new Firmware(base).decoded, rt = sectionsOf(old).find(s => s.name === 'RTOS')!;
  const end = rt.offset + rt.size, recovered = new Uint8Array(old.length);
  recovered.set(rebuilt.decoded.subarray(0, end)); recovered.set(rebuilt.decoded.subarray(end + rebuilt.growth), end);
  new DataView(recovered.buffer).setUint32(rt.offset - 4, rt.size, true);
  for (const p of d.probes) { const cell = vaOffset(old, d.table + p.id * 4, 4); recovered.set(old.subarray(cell, cell + 4), cell); }
  need(same(recovered, old) && sha(recovered) === d.baseDecodedSha256, 'Reversing diagnostic did not recover verified base');
  // The independent script applies the ordinary package checker to the pristine base,
  // then reconstructs diagnostics separately; the ordinary zero-padding rule stays intact.
  const independent = JSON.parse(runPython(python, ['-B', '-c', INDEPENDENT, ROOT, codec, officialPath, out, persist ? 'persist' : 'read-only'])) as { candidateSha256: string; independentExactReconstruction: boolean };
  need(independent.candidateSha256 === sha(candidate) && independent.independentExactReconstruction, 'Independent verification result mismatch');
  return { pristineBaseFreshEngineVerified: true, reverseBaseExact: true, deterministicReapplyByteIdentical: true, independentDecoderVerified: true,
    candidateGeneralEngine: { kind: candidateSummary.kind, verified: candidateSummary.verified, expected: true, reason: 'Production recipe has no diagnostic multi-axis input; complete production rebuild differs. General app write authorization stays disabled.' }, checks: rebuilt.checks };
}

async function main() {
  const args = process.argv.slice(2).filter(a => a !== '--'), options = new Map<string, string>();
  for (let i = 0; i < args.length; i += 2) { need(args[i].startsWith('--') && args[i + 1] && !options.has(args[i]), 'Use unique --name VALUE arguments'); options.set(args[i], args[i + 1]); }
  const allowed = new Set(['--official', '--out', '--current-pack', '--references', '--python', '--codec', '--verify']);
  need([...options.keys()].every(k => allowed.has(k)), 'Unknown command-line option');
  need(options.has('--official') && (options.has('--out') || options.has('--verify')), 'usage: vite-node build-t-colour.mts --official OFFICIAL --out NEW_DIR [--current-pack PACK --references DIR --python PYTHON --codec DIR]; or --official OFFICIAL --verify EXISTING_DIR');
  const officialPath = resolve(options.get('--official')!), out = resolve(options.get('--verify') ?? options.get('--out')!);
  const currentPath = resolve(options.get('--current-pack') ?? join(ROOT, 'research/gr3-210/inputs/current-pack-mtf.bin'));
  const references = resolve(options.get('--references') ?? join(ROOT, 'research/gr3-210/reference-pinned'));
  const python = resolve(options.get('--python') ?? join(ROOT, 'research/gr3-210/toolchain/Scripts/python.exe'));
  const codec = resolve(options.get('--codec') ?? join(ROOT, 'research/gr3-210/independent-codec'));
  if (options.has('--verify')) { console.log(JSON.stringify(await verifyOutput(officialPath, out, python, codec), null, 2)); return; }
  need(!existsSync(out), 'Output directory exists; choose a fresh path'); checkCodec(codec);
  const official = new Uint8Array(readFileSync(officialPath)), current = new Uint8Array(readFileSync(currentPath));
  need(sha(official) === GR3_210.sha256 && official.length === GR3_210.size, 'Exact official GR III 2.10 identity mismatch');
  need(sha(current) === CURRENT, 'Pinned current MTF pack SHA-256 mismatch');
  const manifestBytes = readFileSync(join(references, 'manifest.json')); need(sha(manifestBytes) === REFERENCES, 'Pinned reference manifest mismatch');
  const referenceManifest = JSON.parse(manifestBytes.toString('utf8')) as { references: { id: string; coefficients: string }[]; artifacts: { path: string; sha256: string }[] };
  const pinned = new Map<string, Gr3xFilmLook>();
  for (const [id, pin] of Object.entries(PINS)) {
    const ref = referenceManifest.references.find(r => r.id === id), artifact = referenceManifest.artifacts.find(a => a.path === ref?.coefficients);
    need(ref && artifact && ref.coefficients === `coefficients/${id}.json`, `Invalid pinned reference path: ${id}`);
    const bytes = readFileSync(join(references, ref.coefficients)); need(sha(bytes) === artifact.sha256, `Reference artifact hash mismatch: ${id}`);
    const film = JSON.parse(bytes.toString('utf8')) as Gr3xFilmLook; need(payload(film) === pin, `Reference quantized payload mismatch: ${id}`); pinned.set(id, film);
  }
  const sources = sourceSnapshot(), currentSpatialProfile = historicalProfile();
  console.log('Verifying pinned return pack with declared historical v3 profile and a fresh Engine');
  const currentSummary = await (await Engine.open(official)).inspect(current); need(currentSummary.verified, 'Pinned current pack does not reconstruct under the declared historical profile');
  const { decoded: currentDecoded, looks, features } = recipes(current);
  need(looks.filmCount === 20 && looks.films?.length === 20 && looks.films.every(f => f.filmMtf), 'Expected exact twenty-film MTF source pack');
  need(features.round10 && features.round9 && features.round8 && features.round7 && !features.lookLayout, 'Expected default-order R10 source pack');
  for (const id of ['v3-portra-400', 'v3-cinestill-800t', 'v3-gold-200']) {
    const ref = pinned.get(id)!; need(looks.films.find(f => f.name === ref.name && payload(f) === PINS[id]), `Source pack differs from pinned colour: ${id}`);
  }
  const original = new Firmware(official).decoded;
  const standardMatrixAddress = wordVA(original, wordVA(original, 0x55018d94 + 11 * 4) + 4);
  const standardMatrixBytes = readVA(original, standardMatrixAddress, 18), sm = new DataView(standardMatrixBytes.buffer);
  const matrix = Array.from({ length: 9 }, (_, i) => sm.getInt16(i * 2, true));
  const neutral = quantizeSlot({ M1: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], ck: [0, 1, 2].map(() => Float64Array.from({ length: 17 }, (_, i) => i / 16)) }, matrix);
  const neutralPreset = { matrixQ13: Array.from(neutral.matrixQ13), curves: neutral.curves.map(c => Array.from(c)) as [number[], number[], number[]] };
  const films: Gr3xFilmLook[] = RETAIN.map(name => {
    const source = name === 'Gold +2 EV (approved)' ? pinned.get('gold-plus2-approved') : looks.films!.find(f => f.name === name);
    need(source && source.name === name && source.preset, `Retained colour missing: ${name}`);
    return { name, ...(source.icon ? { icon: source.icon } : {}), preset: source.preset };
  });
  for (let k = 0; k < 14; k++) films.push({ name: `MA ${String.fromCharCode(65 + k)} ${LABELS[k]}`, preset: neutralPreset });
  need(films.length === 20 && films.every(f => !f.grain && !f.filmMtf && !f.defaults && f.halation === undefined), 'Textures/default overrides must be absent on all films');
  const res = readRes(currentDecoded), pictures = features.pictures.map((name, k) => {
    const jpeg = resFile(currentDecoded, gr3xPicturePath(k), res); need(jpeg, `Missing source end-screen picture ${k}`); return { name, jpeg, id: features.pictureIds[k] };
  });
  const textureDisabledProfile = diagnosticProfile();
  const baseLooks: Gr3xLookOptions = { displayRevision: 3, monoReplicas: false, filmCount: 20, ownParameters: true, films };
  const baseFeatures = { round7: true, round8: true, round9: true, round10: true, pictures, pictureMenu: features.pictureMenu };
  console.log('Building ordinary R10 base: six exact colour comparators plus fourteen identical neutral probes; all textures disabled');
  const base = await buildGr3xTestFirmware(official, [], baseLooks, planGr3xMenu(features.ratios), baseFeatures);
  need(Object.values(base.report.checks).every(v => v === true), 'Ordinary base container self-check failed');
  const baseSummary = await (await Engine.open(official)).inspect(base.bytes); need(baseSummary.verified && baseSummary.slots.length === 20, 'Fresh Engine does not reconstruct pristine base');
  need('lookEntries' in base.manifest && 'addedLooks' in base.manifest, 'Expected image-control patch manifest');
  const baseDecoded = new Firmware(base.bytes).decoded, baseRtos = sectionsOf(baseDecoded).find(s => s.name === 'RTOS')!;
  const table = base.manifest.lookEntries.films?.multiAxisTable; need(table, 'Missing R10 multi-axis table');
  const jpeg = base.manifest.lookEntries.jpeg; need(jpeg?.halationLooks && !Object.keys(jpeg).some(k => /grain|filmMtf|date/i.test(k)), 'Unexpected grain/MTF/date module in base');
  for (let k = 0; k < 20; k++) need(readVA(baseDecoded, jpeg.halationLooks + k * 520, 8).every(v => v === 0), `Nonzero halation gain in film ${64 + k}`);
  need(!base.manifest.adjSoftFocus && !base.manifest.dateImprint && !base.manifest.grainRow, 'Soft focus/date/grain-row must be omitted');
  const a = base.manifest.addedLooks[6];
  for (const p of base.manifest.addedLooks.slice(6)) {
    need(same(readVA(baseDecoded, wordVA(baseDecoded, p.record + 4), 18), standardMatrixBytes), 'Probe pre-matrix differs from Standard');
    need(same(readVA(baseDecoded, p.curves, 1536), readVA(baseDecoded, a.curves, 1536)) && !p.postQ9 && !p.tealRecords, 'Probe curves/post/teal paths differ');
  }
  const d = descriptor(base.bytes, baseDecoded, table, original), recipeBytes = Buffer.from(JSON.stringify(d) + '\n', 'utf8');
  const candidate = applyDiagnostic(base.bytes, d, recipeBytes);
  need(same(readVA(candidate.decoded, table, 70 * 4), readVA(baseDecoded, table, 70 * 4)), 'Native and retained film table entries changed');
  for (const source of sources) need(sha(readFileSync(join(ROOT, source.path), 'utf8').replace(/\r\n/g, '\n')) === source.sha256Lf, `Source changed during generation: ${source.path}`);
  mkdirSync(out, { recursive: true });
  writeFileSync(join(out, 'BASE-VERIFIED.bin'), base.bytes, { flag: 'wx' }); writeFileSync(join(out, 'UNVALIDATED.bin'), candidate.bytes, { flag: 'wx' });
  writeFileSync(join(out, 'RETURN-CURRENT-MTF.bin'), current, { flag: 'wx' }); writeFileSync(join(out, 'diagnostic-recipe.json'), recipeBytes, { flag: 'wx' });
  writeJson(out, 'base-patch-manifest.json', base.manifest); writeJson(out, 'base-build-report.json', base.report);
  const report = { schema: 1, kind: 'GR3-TCOLOUR-1', status: 'UNVALIDATED-REVIEW-PENDING', camera: 'GR III', firmware: '2.10', hardwareTested: false, deviceIoPerformed: false,
    input: { officialSha256: GR3_210.sha256, currentPackSha256: CURRENT, referencesSha256: REFERENCES, independentCodecCommit: CODEC },
    candidate: { filename: 'UNVALIDATED.bin', sha256: sha(candidate.bytes), bytes: candidate.bytes.length, decodedSha256: sha(candidate.decoded), additionalRtosGrowth: candidate.growth },
    base: { filename: 'BASE-VERIFIED.bin', sha256: sha(base.bytes), decodedSha256: sha(baseDecoded), freshEngineVerified: true, report: 'base-build-report.json' },
    profiles: { sourcePack: currentSpatialProfile, baseAndCandidate: textureDisabledProfile, globalScope: 'Process-local CLI override; fresh Engine per profile; ordinary app defaults may not recognize the experimental profile.' },
    textureDisabled: { noGrainModule: true, noMtfModule: true, allTwentyFilmHalationGainsZero: true, dateModuleOmitted: true, adjSoftFocusOmitted: true, allFilmDefaultsNeutral: true, rawStashCannotSelectNonzeroGain: true },
    slots: films.map((f, i) => ({ id: 64 + i, name: f.name, colourPayloadSha256: payload(f), retainedColour: i < 6, textures: 'disabled' })),
    probes: d.probes.map(p => ({ ...p, coefficients: 'diagnostic-recipe.json' })), ratios: features.ratios, guard: 'R10 retained; normal film/RAW mappings and native fallbacks',
    whitelist: candidate.ranges, extension: { address: d.extensionAddress, dataBytes: d.dataBytes, recipeDecodedOffset: candidate.recipeOffset, recipeBytes: recipeBytes.length, checksumDecodedOffset: baseRtos.offset + baseRtos.size + candidate.growth - 4 },
    resetRequired: 'Complete section5 of docs/GR3_HDF_210_TEST.txt before entering AND leaving this changed twenty-slot library; no U-mode probe saves.',
    returnPack: { file: 'RETURN-CURRENT-MTF.bin', sha256: CURRENT, installedIdentityEstablished: false },
    killCriterion: 'After registered B versus A and repeat A with fixed settings: if B matches A within repeat-control/JPEG variation, close this direction for the tested RAW route. No fitter before positive pixel evidence.',
    limitations: ['No camera test or flashing.', 'General Engine must return unknown/verified=false for the diagnostic extension; no general app write enable.', 'Source block group order and adjacent-index patterns are hypotheses.', 'Production fingerprints do not cover multi-axis diagnostics; full reset is mandatory.', 'All native RAW development controls must be identical; texture disabling does not neutralize arbitrary native exposure/WB/contrast edits.'],
    repository: { head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim(), hashEncoding: 'UTF-8 with CRLF normalized to LF', sources },
  };
  writeJson(out, 'diagnostic-manifest.json', report);
  console.log('Running fresh-Engine base/candidate checks, reverse/reapply, pinned independent reconstruction and bounded updater/loader regression');
  const verification = await verifyOutput(officialPath, out, python, codec, true); writeJson(out, 'verification.json', verification);
  writeFileSync(join(out, 'SHA256SUMS.txt'), `${sha(candidate.bytes)}  UNVALIDATED.bin\n${sha(base.bytes)}  BASE-VERIFIED.bin\n${CURRENT}  RETURN-CURRENT-MTF.bin\n`, { encoding: 'utf8', flag: 'wx' });
  writeFileSync(join(out, 'TEST-CARD.txt'), testCard(report.slots, sha(candidate.bytes)), { encoding: 'utf8', flag: 'wx' });
  console.log(JSON.stringify({ status: 'HOST-VERIFIED-REVIEW-PENDING', output: out, candidate: report.candidate, slots: report.slots.map(s => `${s.id} ${s.name}`), textureDisabled: report.textureDisabled, verification, hardwareTested: false, finalUpdateFilenameAssigned: false }, null, 2));
}

function testCard(slots: { id: number; name: string }[], candidateHash: string) {
  return `T-COLOUR / GR III 2.10 / development diagnostics only\nHOST-VERIFIED-REVIEW-PENDING: UNVALIDATED.bin is not a final camera update artifact.\nCandidate SHA256: ${candidateHash}\nThe agent does not flash or write devices. Root review and full-suite gate precede any final filename.\n\nCAPACITY AND RESET — COMPLETE SECTION5, BEFORE INSTALLING AND BEFORE RESTORING\nThis library has six retained films and fourteen probes. It is not the full current film pack. All film IDs may change meaning. Camera settings survive firmware changes.\n1. Set aspect ratio to 3:2.\n2. Set Image Control to a native look, such as Standard, and Clarity to 0.\n3. Turn shooting timestamp Off; set End Screen Picture to Original. Before a reduced/changed film library, remove added-film references from U1/U2/U3 or resave those modes with native looks.\n   Before returning from round12+ to round11 or earlier, film parameter/halation records restart from their current values; those older versions cannot read the newer records.\n   Before returning from round13+ to round12 or earlier, choose one of the first two timestamp styles, set Follow Camera Direction On, then turn timestamp Off. Changed presets restart from defaults.\n   When leaving a film build for one without films, selected sets may become Standard while retaining film parameter numbers; reset them.\n4. Setup > Reset > Restore Default Settings.\n5. Only then change to the reviewed test firmware or return firmware. Follow docs/GR3_HDF_210_TEST.txt section5 for the full original instructions. Stay on2.10; never upgrade to2.20.\nDo not save probe films into U1/U2/U3. Keep a copy of RETURN-CURRENT-MTF.bin; its SHA256 is ${CURRENT}. This file is a verified return reference, not proof of what is installed now.\n\nTEST\nShoot one DNG containing strong unclipped hue patches at several brightness levels, neutral steps, and a smooth hue ramp. Use fixed illumination, exposure and WB; use the same DNG for every development.\nSet all native RAW controls consistently: exposure/WB/contrast/saturation/Hue/sharpness/Clarity and correction/NR choices. Probes have the same Standard pre-matrix and neutral curves/post path; only their multi-axis source blocks differ.\nAll20 slots have no grain or MTF module and zero halation gain tables, independent of the RAW stash. Date and ADJ Soft Focus modules are omitted. RAW Halation editing is not assumed or required.\nFirst develop native Standard, MA A control, MA B all, then MA A control again. Record output filenames and settings.\nKILL: if B matches A after confirming the selected slots/settings and repeat A, stop. Return the DNG plus all four original JPEGs. Different DQT tables require comparison against repeat-A variation; no new fitter follows an inactive result.\nIf B visibly/systematically changes pixels, develop C through N from the same DNG without changing other settings. C–H encode serialized group index bits; I–K row-sum scaling; L group0 doubling; M/N adjacent-index hypotheses, not proven neighbouring hue sectors.\nAlso develop the six retained texture-off comparators as requested by the common card for model/camera comparison. Approved Gold is separately named; Portra colour is unchanged.\nReturn original DNG/JPEG files, filename-to-slot log, any camera problems, and this build's SHA256. No claims of stage order, film fidelity or hardware safety follow from host verification.\n\nSLOTS\n${slots.map(s => `${s.id}  ${s.name}`).join('\n')}\n\nRETURN\nRepeat the complete section5 reset before restoring RETURN-CURRENT-MTF.bin under the declared v3 profile.\n`;
}

function selfTest() {
  const first = [420, 76, 16, 38, 458, 16, 38, 76, 398];
  const identity = [1024, 0, 0, 0, 1024, 0, 0, 0, 1024];
  const standard = [...first, ...Array.from({ length: 59 }, () => identity).flat()];
  const blocks = probeBlocks(standard);
  assert.equal(blocks.length, 14, 'A–N requires fourteen source blocks');
  assert.deepEqual(blocks[0], standard, 'A preserves every Standard coefficient');
  assert.ok(blocks.every(b => b.length === 540 && b.every(x => Number.isInteger(x) && x >= -2048 && x <= 2047)));
  for (let g = 0; g < 60; g++) {
    assert.notDeepEqual(blocks[1].slice(g * 9, g * 9 + 9), standard.slice(g * 9, g * 9 + 9));
    for (let k = 0; k < 6; k++) {
      const actual = blocks[2 + k].slice(g * 9, g * 9 + 9);
      assert.deepEqual(actual, ((g >> k) & 1) ? blocks[1].slice(g * 9, g * 9 + 9) : standard.slice(g * 9, g * 9 + 9));
    }
    for (const [index, numerator] of [[8, 2], [9, 3], [10, 5]]) for (let row = 0; row < 3; row++)
      assert.equal(blocks[index].slice(g * 9 + row * 3, g * 9 + row * 3 + 3).reduce((a, b) => a + b), (g ? 1024 : 512) * numerator / 4);
  }
  assert.deepEqual(blocks[11].slice(0, 9), first.map(x => x * 2));
  assert.deepEqual(blocks[11].slice(9), standard.slice(9));
  assert.deepEqual(blocks[12].slice(25 * 9, 30 * 9), blocks[13].slice(30 * 9, 35 * 9));
  assert.deepEqual(blocks[13].slice(25 * 9, 30 * 9), blocks[12].slice(30 * 9, 35 * 9));
  assert.throws(() => probeBlocks(standard.slice(1)), /540/);
  const invalid = [...standard]; invalid[9] = 4096; assert.throws(() => probeBlocks(invalid), /coefficient/);
  console.log('T-colour probe codec self-test passed');
}

if (process.argv.includes('--self-test')) selfTest();
else await main();
