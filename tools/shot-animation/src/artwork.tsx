import type {ReactNode} from 'react';

export const ink = '#1c2829';
export const cream = '#fff1d6';
export const coral = '#ed795e';
export const mint = '#a3d8bf';
export const gold = '#e8bb63';

export function Tile({children, label}: {children: ReactNode; label: string}) {
  return <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 176" width="240" height="176" aria-label={label} role="img" className="tile-svg">
    <defs>
      <linearGradient id="paper" x2="0.2" y2="1"><stop stopColor="#fff9e9"/><stop offset="1" stopColor="#e2dac4"/></linearGradient>
      <linearGradient id="metal" x2="0" y2="1"><stop stopColor="#414d4a"/><stop offset="1" stopColor="#1c2829"/></linearGradient>
    </defs>
    {children}
  </svg>;
}

export function Print({x = 0, y = 0, scale = 1, rotate = 0, opacity = 1}: {x?: number; y?: number; scale?: number; rotate?: number; opacity?: number}) {
  return <g transform={`translate(${x} ${y}) rotate(${rotate}) scale(${scale})`} opacity={opacity}>
    <rect x="-27" y="-29" width="56" height="69" rx="3" fill={ink} opacity=".18" transform="translate(2 4)"/>
    <rect x="-28" y="-30" width="56" height="69" rx="3" fill="url(#paper)" stroke={ink} strokeWidth="1.3"/>
    <rect x="-22" y="-24" width="44" height="43" rx="1" fill="#9ebfaf"/>
    <circle cx="11" cy="-12" r="6" fill="#ffe0a4"/>
    <path d="M-22 10 -6-8 7 8 16 0 22 8V19H-22Z" fill="#3d6559"/>
    <path d="M-22 16 1 3 22 15V19H-22Z" fill="#24473f"/>
    <path d="M-16 27h21m4 0h6" stroke="#7c8174" strokeWidth="2" strokeLinecap="round"/>
  </g>;
}

export function Spark({x,y,size = 5,opacity = 1}: {x:number;y:number;size?:number;opacity?:number}) {
  return <path d={`M${x-size} ${y}Q${x} ${y} ${x} ${y-size}Q${x} ${y} ${x+size} ${y}Q${x} ${y} ${x} ${y+size}Q${x} ${y} ${x-size} ${y}`} fill={gold} opacity={opacity}/>;
}

export function Robot({y = 0, tilt = 0, blink = false, happy = false, arm = 0}: {y?: number;tilt?: number;blink?: boolean;happy?: boolean;arm?: number}) {
  return <g transform={`translate(0 ${y}) rotate(${tilt} 118 112)`}>
    <ellipse cx="121" cy="153" rx="45" ry="5" fill={ink} opacity=".17"/>
    <path d="M97 141v10h13v-10m24 0v10h13v-10" fill={ink} stroke={ink} strokeWidth="4" strokeLinejoin="round"/>
    <path d="M86 117l-12 12-9-5" fill="none" stroke={ink} strokeWidth="7" strokeLinecap="round"/>
    <path d="M156 117l10 4 11-14" transform={`rotate(${-arm} 156 117)`} fill="none" stroke={ink} strokeWidth="7" strokeLinecap="round"/>
    <rect x="84" y="91" width="76" height="53" rx="12" fill={cream} stroke={ink} strokeWidth="3"/>
    <rect x="92" y="103" width="60" height="23" rx="4" fill={ink}/>
    <path d="M98 109h48" stroke="#52645c" strokeWidth="2"/>
    <rect x="102" y="130" width="28" height="5" rx="2" fill={coral}/>
    <circle cx="141" cy="133" r="3" fill={mint} stroke={ink} strokeWidth="1"/>
    <path d="M119 44v-9" stroke={ink} strokeWidth="3"/><circle cx="119" cy="33" r="4" fill={coral} stroke={ink} strokeWidth="2"/>
    <rect x="75" y="52" width="9" height="25" rx="4" fill={gold} stroke={ink} strokeWidth="2.5"/>
    <rect x="155" y="52" width="9" height="25" rx="4" fill={gold} stroke={ink} strokeWidth="2.5"/>
    <rect x="81" y="44" width="77" height="48" rx="13" fill={mint} stroke={ink} strokeWidth="3"/>
    <path d="M89 51h62" stroke="#cee9d6" strokeWidth="2" strokeLinecap="round"/>
    <rect x="87" y="57" width="29" height="21" rx="6" fill={cream} stroke={ink} strokeWidth="3"/>
    <rect x="123" y="57" width="29" height="21" rx="6" fill={cream} stroke={ink} strokeWidth="3"/>
    <path d="M116 63q3-3 7 0" fill="none" stroke={ink} strokeWidth="3"/>
    {blink ? <path d="M96 68h11m24 0h11" stroke={ink} strokeWidth="3" strokeLinecap="round"/> : happy ? <path d="M96 69q5-9 11 0m24 0q5-9 11 0" fill="none" stroke={ink} strokeWidth="2.7" strokeLinecap="round"/> : <><rect x="101" y="62" width="5" height="10" rx="2" fill={ink}/><rect x="134" y="62" width="5" height="10" rx="2" fill={ink}/></>}
    <path d={happy ? 'M114 83q6 6 12 0' : 'M116 84h8'} fill="none" stroke={ink} strokeWidth="2" strokeLinecap="round"/>
  </g>;
}

export function Badge({children, x = 120, y = 20, opacity = 1}: {children: ReactNode;x?:number;y?:number;opacity?:number}) {
  return <g opacity={opacity}><rect x={x-49} y={y-11} width="98" height="22" rx="11" fill={ink}/><text x={x} y={y+3.5} fill={cream} textAnchor="middle" fontFamily="Arial, sans-serif" fontSize="9" fontWeight="700" letterSpacing=".7">{children}</text></g>;
}
