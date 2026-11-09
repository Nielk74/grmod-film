import { renderPreviewPixels } from './preview';
import type { DetailOptions } from './preview';
import type { PreviewPixels } from './pixels';
import type { color } from '@grmod/core';

const scope = self as unknown as DedicatedWorkerGlobalScope;
scope.onmessage = (event: MessageEvent<{ source: PreviewPixels; params?: color.SlotParams; options: DetailOptions }>) => {
  try {
    const { source, params, options } = event.data;
    const result = renderPreviewPixels(source, params, options);
    scope.postMessage({ result }, [result.before.data.buffer, result.after.data.buffer]);
  } catch (error) { scope.postMessage({ error: error instanceof Error ? error.message : String(error) }); }
};
