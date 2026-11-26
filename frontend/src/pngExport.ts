import { methods, numberText, statuses, type Snapshot } from './domain'

export type ExperimentPngKind = 'simulation' | 'graph'

export interface ExperimentPngOptions {
  snapshot: Snapshot
  kind: ExperimentPngKind
  displayTitle?: string
  currentTime?: number
  plotDescription?: string
  plotSeries?: { label: string; color: string }[]
}

const SVG_NS = 'http://www.w3.org/2000/svg'
const EXPORT_WIDTH = 1200
const EXPORT_PADDING = 48
const EXPORT_CARD_PADDING = 12
const SOURCE_STYLE_PROPERTIES = [
  'color',
  'display',
  'dominant-baseline',
  'fill',
  'fill-opacity',
  'fill-rule',
  'font-family',
  'font-size',
  'font-style',
  'font-weight',
  'opacity',
  'paint-order',
  'shape-rendering',
  'stop-color',
  'stop-opacity',
  'stroke',
  'stroke-dasharray',
  'stroke-dashoffset',
  'stroke-linecap',
  'stroke-linejoin',
  'stroke-miterlimit',
  'stroke-opacity',
  'stroke-width',
  'text-anchor',
  'vector-effect',
  'visibility',
] as const

function escapeXml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;')
}

function wrapLine(value: string, width = 72): string[] {
  const chunks: string[] = []
  let rest = value.trim().replace(/\s+/g, ' ')
  while (Array.from(rest).length > width) {
    const chars = Array.from(rest)
    let breakAt = chars.lastIndexOf(' ', width)
    if (breakAt < Math.floor(width * 0.55)) breakAt = width
    chunks.push(chars.slice(0, breakAt).join('').trim())
    rest = chars.slice(breakAt).join('').trim()
  }
  if (rest) chunks.push(rest)
  return chunks
}

export function localizeSvgFragmentUrls(value: string): string {
  return value.replace(/url\((['"]?)([^)'\"]*)\1\)/g, (match, _quote: string, reference: string) => {
    const fragment = reference.slice(reference.lastIndexOf('#') + 1)
    return reference.includes('#') && fragment ? `url(#${fragment})` : match
  })
}

function inputRows(snapshot: Snapshot): string[] {
  const { experiment } = snapshot
  if (!experiment.variables.length) return ['입력 변수가 별도로 지정되지 않았습니다.']
  return experiment.variables.flatMap((variable) =>
    wrapLine(`${variable.label} = ${numberText(experiment.values[variable.key])} ${variable.unit}`),
  )
}

function metadataRows(options: ExperimentPngOptions): { text: string; kind?: 'heading' | 'body'; color?: string }[] {
  const { snapshot, kind, currentTime, plotDescription, plotSeries } = options
  const { experiment, run } = snapshot
  const passed = run.checks.filter((check) => check.passed).length
  const rows: { text: string; kind?: 'heading' | 'body' }[] = [
    {
      text: `${experiment.category} · ${experiment.model.replaceAll('_', ' ')} · ${methods[experiment.method]} · Δt ${numberText(experiment.dt)} s`,
    },
  ]
  if (currentTime !== undefined && Number.isFinite(currentTime)) {
    rows.push({ text: `표시 시각 · ${numberText(currentTime)} s` })
  }
  if (kind === 'graph' && plotDescription) {
    rows.push({ text: '플롯 정보', kind: 'heading' })
    rows.push(...wrapLine(plotDescription).map((text) => ({ text })))
  }
  if (kind === 'graph' && plotSeries?.length) {
    rows.push({ text: '곡선 및 계열', kind: 'heading' })
    rows.push(...plotSeries.map((series) => ({ text: series.label, color: series.color })))
  }
  rows.push({ text: '입력 변수 · SI 단위', kind: 'heading' })
  rows.push(...inputRows(snapshot).map((text) => ({ text })))
  rows.push({ text: '모델 가정', kind: 'heading' })
  if (experiment.assumptions.length) {
    rows.push(...experiment.assumptions.flatMap((assumption) =>
      wrapLine(`• ${assumption}`).map((text) => ({ text })),
    ))
  } else {
    rows.push({ text: '별도 가정이 지정되지 않았습니다.' })
  }
  rows.push({ text: '검증 상태', kind: 'heading' })
  rows.push({
    text: `${statuses[run.status]} (${run.status}) · 통과 ${passed}/${run.checks.length}개 항목`,
  })
  for (const check of run.checks) {
    const marker = check.passed ? '✓' : '✗'
    rows.push(...wrapLine(`${marker} ${check.label} · ${check.detail}`).map((text) => ({ text })))
  }
  return rows
}

function sourceSvgFrame(sourceSvg: string, x: number, y: number, width: number, height: number): string {
  const match = sourceSvg.match(/^\s*<svg\b([^>]*?)(\/?)>/i)
  if (!match) throw new Error('SVG 그래프 또는 시뮬레이션을 찾을 수 없습니다.')

  const attributes = match[1]
    .replace(/\s+(?:xmlns|x|y|width|height|preserveAspectRatio)=(['"]).*?\1/gi, '')
    .replace(/\s*\/$/, '')
  const closingStart = sourceSvg.toLowerCase().lastIndexOf('</svg>')
  const content = match[2] === '/' || closingStart < match[0].length
    ? ''
    : sourceSvg.slice(match[0].length, closingStart)
  return `<svg xmlns="${SVG_NS}"${attributes} x="${x}" y="${y}" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet">${content}</svg>`
}

function sourceDimensions(sourceSvg: string): [number, number] {
  const viewBox = sourceSvg.match(/\bviewBox=(['"])([^'"]+)\1/i)?.[2]
  if (viewBox) {
    const [width, height] = viewBox.trim().split(/[\s,]+/).slice(2, 4).map(Number)
    if (width > 0 && height > 0) return [width, height]
  }
  const width = Number(sourceSvg.match(/\bwidth=(['"])([\d.]+)/i)?.[2])
  const height = Number(sourceSvg.match(/\bheight=(['"])([\d.]+)/i)?.[2])
  return [width > 0 ? width : 700, height > 0 ? height : 278]
}

/** Build a self-contained SVG sheet that the browser can rasterize to PNG. */
export function buildExperimentPngSvgDocument(sourceSvg: string, options: ExperimentPngOptions): string {
  const title = options.displayTitle?.trim() || options.snapshot.experiment.title
  const titleLines = wrapLine(title, 38)
  const subtitle = `${options.snapshot.experiment.category} · ${options.snapshot.experiment.model.replaceAll('_', ' ').toUpperCase()} · revision ${options.snapshot.revision}`
  const rows = metadataRows(options)
  const lineHeight = 25
  const rowsTop = 128 + Math.max(0, titleLines.length - 1) * 38
  const headerHeight = rowsTop + rows.length * lineHeight + 14
  const imageWidth = EXPORT_WIDTH - EXPORT_PADDING * 2 - EXPORT_CARD_PADDING * 2
  const [sourceWidth, sourceHeight] = sourceDimensions(sourceSvg)
  const imageHeight = Math.max(120, imageWidth * sourceHeight / sourceWidth)
  const imageY = headerHeight + EXPORT_CARD_PADDING
  const documentHeight = imageY + imageHeight + EXPORT_CARD_PADDING + 34
  const source = sourceSvgFrame(
    sourceSvg,
    EXPORT_PADDING + EXPORT_CARD_PADDING,
    imageY,
    imageWidth,
    imageHeight,
  )
  const metadata = rows.map((row, index) => {
    const y = rowsTop + index * lineHeight
    const color = row.kind === 'heading' ? '#c4ee83' : '#c6d1d8'
    const weight = row.kind === 'heading' ? '700' : '400'
    const size = row.kind === 'heading' ? '17' : '15'
    const marker = row.color
      ? `<line x1="${EXPORT_PADDING}" y1="${y - 5}" x2="${EXPORT_PADDING + 18}" y2="${y - 5}" stroke="${escapeXml(row.color)}" stroke-width="3"/>`
      : ''
    const textX = row.color ? EXPORT_PADDING + 27 : EXPORT_PADDING
    return `${marker}<text x="${textX}" y="${y}" fill="${color}" font-family="Arial, sans-serif" font-size="${size}" font-weight="${weight}">${escapeXml(row.text)}</text>`
  }).join('')
  const titleText = titleLines.map((line, index) =>
    `<text x="${EXPORT_PADDING}" y="${51 + index * 38}" fill="#f0f4f6" font-family="Arial, sans-serif" font-size="30" font-weight="700">${escapeXml(line)}</text>`,
  ).join('')
  const subtitleY = 82 + Math.max(0, titleLines.length - 1) * 38

  return `<svg xmlns="${SVG_NS}" width="${EXPORT_WIDTH}" height="${documentHeight}" viewBox="0 0 ${EXPORT_WIDTH} ${documentHeight}" role="img" aria-label="${escapeXml(title)} PNG 내보내기"><title>${escapeXml(title)}</title><rect width="100%" height="100%" fill="#11181e"/>${titleText}<text x="${EXPORT_PADDING}" y="${subtitleY}" fill="#94a5b0" font-family="Arial, sans-serif" font-size="15">${escapeXml(subtitle)}</text>${metadata}<rect x="${EXPORT_PADDING - 10}" y="${headerHeight}" width="${EXPORT_WIDTH - EXPORT_PADDING * 2 + 20}" height="${imageHeight + EXPORT_CARD_PADDING * 2}" rx="8" fill="#182129" stroke="#34434e"/>${source}</svg>`
}

function serializeSvgWithComputedStyles(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', SVG_NS)
  const originals = [svg, ...Array.from(svg.querySelectorAll('*'))]
  const copies = [clone, ...Array.from(clone.querySelectorAll('*'))]
  originals.forEach((original, index) => {
    const computed = window.getComputedStyle(original)
    const style = (copies[index] as SVGElement).style
    for (const property of SOURCE_STYLE_PROPERTIES) {
      const value = computed.getPropertyValue(property)
      if (value) style.setProperty(property, localizeSvgFragmentUrls(value))
    }
  })
  return new XMLSerializer().serializeToString(clone)
}

function loadSvgImage(svg: string): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }))
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('PNG 미리보기를 그리지 못했습니다.'))
    }
    image.src = url
  })
}

function canvasPng(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('PNG 파일을 만들지 못했습니다.'))
    }, 'image/png')
  })
}

function safeFilePart(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'experiment'
}

/** Export the currently displayed SVG and run details without recalculating the model. */
export async function downloadExperimentPng(
  svg: SVGSVGElement,
  options: ExperimentPngOptions,
): Promise<void> {
  const sourceSvg = serializeSvgWithComputedStyles(svg)
  const document = buildExperimentPngSvgDocument(sourceSvg, options)
  const image = await loadSvgImage(document)
  const canvas = window.document.createElement('canvas')
  canvas.width = EXPORT_WIDTH
  canvas.height = image.naturalHeight
  const context = canvas.getContext('2d')
  if (!context) throw new Error('PNG 캔버스를 사용할 수 없습니다.')
  context.fillStyle = '#11181e'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.drawImage(image, 0, 0)
  const blob = await canvasPng(canvas)
  const url = URL.createObjectURL(blob)
  const anchor = window.document.createElement('a')
  anchor.href = url
  anchor.download = `physis-${safeFilePart(options.snapshot.experiment.model)}-${options.kind}-r${options.snapshot.revision}.png`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
