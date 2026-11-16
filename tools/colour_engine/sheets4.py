import sys, os, json, numpy as np
from common import *
from engine import *
import films4
from sheets2 import sheet
from measure4 import measure, PLANTS

LABELS = {'rich': 'Rich', 'richwarm': 'Rich warm', 'ektar': 'Portra x Ektar'}
SCENES = ['R0000022', 'R0000023', 'R0000027', 'R0000020', 'R0000030', 'R0000005', 'AK000164', 'R0000018']

if __name__ == '__main__':
    ls = {}
    for k, (f, ne) in films4.LOOKS4.items():
        ls[k] = build_lut(f, ne); np.save(os.path.join(OUT, f'lut-portra-{k}.npy'), ls[k])
    cols = [('Standard', 'std'), ('Camera today', None)] + [(LABELS[k], ls[k]) for k in ls]
    sheet('Portra 400', SCENES, cols, wp=380, wl=520, name='sheet-portra-rich')
    res = {}
    for k in ls:
        res[k] = measure('Portra 400', ls[k], sorted(set(PLANTS + SCENES)))
    json.dump(res, open(os.path.join(OUT, 'metrics-portra-v4.json'), 'w'), indent=1)
    def med(k, scene_list, who, key):
        v = [res[k][n][who][key] for n in scene_list if key in res[k][n][who]]
        return np.median(v) if v else float('nan')
    # table: foliage (plant scenes), sky, whites, skin, dE
    pl = [n for n in PLANTS]
    k0 = 'rich'
    print('foliage hue/chroma (median over plant scenes)')
    for who in ('std', 'cam'): print('  ', who, 'h %.0f C %.3f dark h %.0f C %.3f' % (med(k0, pl, who, 'green_h'), med(k0, pl, who, 'green_C'), med(k0, pl, who, 'darkgreen_h'), med(k0, pl, who, 'darkgreen_C')))
    for k in ls: print('  ', k, 'h %.0f C %.3f dark h %.0f C %.3f' % (med(k, pl, 'new', 'green_h'), med(k, pl, 'new', 'green_C'), med(k, pl, 'new', 'darkgreen_h'), med(k, pl, 'new', 'darkgreen_C')))
    print('sky hue/chroma')
    sk = ['R0000022', 'R0000023', 'R0000027']
    for who in ('std', 'cam'): print('  ', who, 'h %.0f C %.3f' % (med(k0, sk, who, 'sky_h'), med(k0, sk, who, 'sky_C')))
    for k in ls: print('  ', k, 'h %.0f C %.3f' % (med(k, sk, 'new', 'sky_h'), med(k, sk, 'new', 'sky_C')))
    print('whites a,b x100 (mean over scenes with whites)')
    wsc = [n for n in res[k0] if 'white_a' in res[k0][n]['cam']]
    for who in ('std', 'cam'): print('  ', who, 'a %.2f b %.2f' % (np.mean([res[k0][n][who]['white_a'] for n in wsc]), np.mean([res[k0][n][who]['white_b'] for n in wsc])))
    for k in ls: print('  ', k, 'a %.2f b %.2f' % (np.mean([res[k][n]['new']['white_a'] for n in wsc if 'white_a' in res[k][n]['new']]), np.mean([res[k][n]['new']['white_b'] for n in wsc if 'white_b' in res[k][n]['new']])))
    print('skin hue shift deg / chroma ratio, mean dE100')
    for k in ls:
        fs = [n for n in res[k] if 'skin_C_ratio' in res[k][n]]
        print('  ', k, 'hue %.1f..%.1f C %.2f..%.2f' % (min(res[k][n]['skin_hue_shift'] for n in fs), max(res[k][n]['skin_hue_shift'] for n in fs), min(res[k][n]['skin_C_ratio'] for n in fs), max(res[k][n]['skin_C_ratio'] for n in fs)),
              'dE', {n: round(res[k][n]['dE100'], 1) for n in SCENES}, 'contrast', round(float(np.mean([res[k][n]['dContrast'] for n in res[k]])), 2))
