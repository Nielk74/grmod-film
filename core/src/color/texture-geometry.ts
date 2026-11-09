// SPDX-License-Identifier: GPL-2.0-only
/** Stored processing geometry, before EXIF display rotation. Width remains the plane/indexing width. */
export type TextureGeometryPolicy = 'sensor' | 'output';
export interface TextureDimensions { width: number; height: number }
/** A preview carries its job's primary main dimensions; omitting/invalidating main uses the 6000 reference. */
export interface TextureGeometry {
  policy: TextureGeometryPolicy;
  main?: TextureDimensions;
  /** Host preview's represented picture at its current pixel scale, before display rotation.
   * Supply when buffer dimensions no longer describe that stored picture (rotation or a 100% subwindow).
   * Native callers use their actual descriptor dimensions and need no override. */
  picture?: TextureDimensions;
}
export const TEXTURE_REFERENCE_SPAN = 6000;
export const aspectSpan = (width: number, height: number): number => Math.max(width, 3 * height / 2);
export function validTextureMain(main: TextureDimensions | undefined): main is TextureDimensions {
  return !!main && Number.isInteger(main.width) && Number.isInteger(main.height) &&
    main.width >= 64 && main.height >= 48 && main.width <= 12000 && main.height <= 12000 &&
    !(main.width & 1) && Math.max(main.width, main.height) >= 1280;
}
export function textureReferenceSpan(geometry: TextureGeometry): number {
  return geometry.policy === 'sensor' && validTextureMain(geometry.main)
    ? aspectSpan(geometry.main.width, geometry.main.height) : TEXTURE_REFERENCE_SPAN;
}
function pictureSpan(width: number, height: number, geometry: TextureGeometry): number {
  const p = geometry.picture;
  return p && Number.isInteger(p.width) && Number.isInteger(p.height) && p.width > 0 && p.height > 0 && p.width <= 12000 && p.height <= 12000
    ? aspectSpan(p.width, p.height) : aspectSpan(width, height);
}
export const textureGrainStep = (width: number, height: number, geometry: TextureGeometry): number =>
  Math.floor(256 * textureReferenceSpan(geometry) / pictureSpan(width, height, geometry));
/** Radius basis in picture pixels, then converted to that picture's actual reduced grid. */
export const textureRadiusSpan = (width: number, height: number, geometry: TextureGeometry, reduction = 1): number =>
  Math.ceil(Math.floor(TEXTURE_REFERENCE_SPAN * pictureSpan(width, height, geometry) / textureReferenceSpan(geometry)) / reduction);
