import {describe, expect, test} from 'vitest';

import {buildInitConfigCommand, bridgeErrorFromExecFailure} from '../src/bridge.js';

describe('bridgeErrorFromExecFailure', () => {
  test('preserves structured Python bridge errors from stdout', () => {
    const result = bridgeErrorFromExecFailure({
      stdout: '{"ok":false,"error":{"code":"file_not_found","message":"文件不存在：contract.pdf"}}'
    });

    expect(result).toEqual({
      ok: false,
      error: {
        code: 'file_not_found',
        message: '文件不存在：contract.pdf'
      }
    });
  });

  test('extracts structured bridge error after noisy OCR logs', () => {
    const result = bridgeErrorFromExecFailure({
      stdout: [
        '[INFO] 2026-06-30 [RapidOCR] Using engine_name: onnxruntime',
        'Stage preprocess failed for run 1, pages [2]: std::bad_alloc',
        '{"ok":false,"error":{"code":"pdf_ocr_memory_exhausted","message":"PDF OCR 内存不足"}}'
      ].join('\n')
    });

    expect(result).toEqual({
      ok: false,
      error: {
        code: 'pdf_ocr_memory_exhausted',
        message: 'PDF OCR 内存不足'
      }
    });
  });

  test('maps unstructured stderr OCR memory failures to retry guidance', () => {
    const result = bridgeErrorFromExecFailure({
      stderr: [
        'Stage preprocess failed for run 1, pages [2]: std::bad_alloc',
        'onnxruntime RuntimeException: Status Message: bad allocation'
      ].join('\n')
    });

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error.code).toBe('pdf_ocr_memory_exhausted');
      expect(result.error.message).toContain('PARSER_DOCLING_ENABLE_OCR');
    }
  });
});

describe('buildInitConfigCommand', () => {
  test('runs the Python CLI initconfig command with the active config and profile', () => {
    const command = buildInitConfigCommand({
      python: 'python-test',
      configPath: 'config.example.yaml',
      profilePath: 'profile.yaml'
    });

    expect(command.executable).toBe('python-test');
    expect(command.args).toEqual([
      '-m',
      'contract_agent.interfaces.cli',
      '--config',
      'config.example.yaml',
      'initconfig',
      '--profile',
      'profile.yaml'
    ]);
  });
});
