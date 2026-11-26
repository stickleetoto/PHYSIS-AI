import { describe, expect, it } from 'vitest'
import { displayStatus, formatEvidenceNumber } from './evidence'

describe('claim evidence labels and numeric display',()=>{
  it('distinguishes support, contradiction, uncertainty and registry evidence',()=>{
    expect(displayStatus('direct')).not.toBe(displayStatus('partial'))
    expect(displayStatus('related')).not.toBe(displayStatus('direct'))
    expect(displayStatus('contradiction')).not.toBe(displayStatus('undecidable'))
    expect(displayStatus('registry_verified')).not.toBe(displayStatus('source_verified'))
  })
  it('prefers the server four-significant-digit representation',()=>{
    expect(formatEvidenceNumber(1.234567,'1.235')).toBe('1.235')
    expect(formatEvidenceNumber(1.234567)).toBe('1.235')
  })
})
