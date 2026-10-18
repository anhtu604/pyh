import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {Anatomy} from '../types';
import type {OrganProps} from './ArterySection';
import {anatomyColors as c, brand} from './palette';

// Anterior view: patient's left is screen-right; the cone leans toward its apex.
const apex = {x: 365, y: 510};
const base = {x: 260, y: 180};
const aortaArchApex = {x: 210, y: 64};
export const heartGeometry = (state: Anatomy['state'], severity: number, frame: number, fps: number) => {
  const disease = state === 'diseased' ? Math.max(0, Math.min(1, severity)) : 0;
  const beatRate = 1.1 + disease * 0.2;
  const phase = (frame / fps * beatRate) % 1;
  const pulse = (p: number) => Math.sin(Math.min(1, p / 0.42) * Math.PI) ** 2;
  const squeeze = pulse(phase);
  const atrialSqueeze = pulse((phase + 0.18) % 1);
  const wallThickness = 24 + disease * 32;
  return {scaleX: 1 - squeeze * 0.055, scaleY: 1 - squeeze * 0.075,
    atrialScale: 1 - atrialSqueeze * 0.045, wallThickness, beatRate,
    apex, base, aortaArchApex,
    // Inset both lateral walls and the apical floor as the LV wall thickens.
    leftVentricleCavity: `M${288 + wallThickness * 0.35} 268 C${399 - wallThickness} 228 ${424 - wallThickness} 336 ${365 - wallThickness * 0.35} ${489 - wallThickness} C${327 + wallThickness * 0.2} 422 ${296 + wallThickness * 0.3} 340 ${288 + wallThickness * 0.35} 268Z`};
};

export const Heart: React.FC<OrganProps & {cutaway?: boolean}> = ({state, severity, emphasizeFlow = false, cutaway = true}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const g = heartGeometry(state, severity, frame, fps);
  return <svg viewBox="40 10 440 540" width="100%" height="100%" role="img" aria-label="Stylised anterior heart"
    data-state={state} data-severity={severity} data-cutaway={cutaway}>
    {/* Filled vessel walls: the arch turns left and descends behind the base. */}
    <path data-vessel="aortic-arch" fill={c.heartDeep}
      d="M270 233 L263 134 C262 94 241 64 210 64 C167 64 141 91 141 130 L141 213 L177 213 L177 130 C177 108 189 100 209 100 C225 100 228 114 228 137 L234 233Z" />
    <path data-vessel="aortic-branches" fill={c.heartMid}
      d="M174 80 L162 42 L180 36 L193 72Z M200 68 L196 24 L215 24 L219 68Z M228 79 L240 38 L258 45 L246 93Z" />
    <path fill={c.heartMid} d="M270 217 L263 134 C262 102 246 77 225 69 C242 90 245 111 245 138 L250 217Z" />
    <path data-vessel="superior-vena-cava" fill={c.vesselDeep} d="M113 82 L153 82 L159 227 L119 235Z" />
    <path fill={c.vesselLight} d="M113 82 L126 82 L132 218 L119 224Z" />
    {/* Only a small left atrial auricle is visible behind the ventricles. */}
    <g data-chamber="atria" transform={`translate(240 207) scale(${g.atrialScale}) translate(-240 -207)`}>
      <path data-chamber="left-atrium" fill={c.heartDeep} d="M322 178 C360 153 395 178 390 218 L348 246 L320 214Z" />
      <path data-chamber="right-atrium" fill={c.heartDeep} d="M163 172 C123 167 96 214 113 265 C120 289 151 306 180 293 L211 226Z" />
      <path fill={c.heartMid} d="M157 184 C126 184 111 217 124 248 C134 267 154 272 169 264 L189 220Z" />
    </g>
    <g data-chamber="ventricles" transform={`translate(${g.apex.x} ${g.apex.y}) scale(${g.scaleX} ${g.scaleY}) translate(${-g.apex.x} ${-g.apex.y})`}>
      <path data-heart-silhouette="true" fill={c.heartDeep}
        d={`M175 185 C215 163 302 165 350 192 C394 219 427 285 409 354 C400 418 377 477 ${g.apex.x} ${g.apex.y} C300 489 240 453 197 408 C147 359 113 301 128 244 C136 216 150 196 175 185Z`} />
      <path data-chamber="left-ventricle" fill={c.heartMid} d="M273 211 C320 188 370 213 391 264 C424 340 379 459 365 510 C318 458 287 384 277 318Z" />
      <path data-chamber="right-ventricle" fill={c.heartMid} d="M175 214 C203 198 250 203 274 226 C262 310 290 405 347 479 C269 451 203 396 166 334 C143 291 141 246 175 214Z" />
      <path fill={c.heartLight} d="M163 240 C155 283 172 321 201 351 C184 313 180 275 195 224Z" />
      {cutaway && <g data-cutaway-chambers="true">
        <path fill={c.vesselDeep} d="M184 245 C207 222 238 228 254 248 C246 307 268 373 300 414 C244 386 205 343 188 303 C177 279 176 260 184 245Z" />
        <path fill={c.chamber} d={g.leftVentricleCavity} data-wall-thickness={g.wallThickness} />
        <path data-septum="true" fill={c.heartLight} d="M267 246 C269 317 287 385 326 442 L310 429 C270 380 251 310 254 248Z" />
      </g>}
      {emphasizeFlow && [0, 1, 2].map((i) => <circle key={i} cx={215 + i * 52}
        cy={285 + ((frame / fps * 75 + i * 25) % 65)} r="7" fill={brand.yellow} />)}
    </g>
    {/* Pulmonary trunk lies anterior to the aortic root and bifurcates at the base. */}
    <path data-vessel="pulmonary-trunk" fill={c.vesselDeep} d="M236 243 C215 219 215 188 229 164 L183 166 L100 184 L94 157 L178 133 L242 133 L279 120 L375 131 L372 161 L285 152 L263 170 C248 192 251 209 266 225Z" />
    <path fill={c.vesselLight} d="M236 231 C224 205 227 183 243 158 L282 137 L371 143 L372 153 L283 148 L254 169 C242 192 245 208 254 219Z" />
  </svg>;
};
