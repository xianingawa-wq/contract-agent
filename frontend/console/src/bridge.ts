import {execFile} from 'node:child_process';
import {promisify} from 'node:util';

const execFileAsync = promisify(execFile);

export type BridgeResponse<T> =
  | {ok: true; data: T}
  | {ok: false; error: {code: string; message: string}};

export type TokenUsage = {
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_total_tokens: number;
};

export type ChatData = {
  reply: string;
  usage: TokenUsage;
};

export async function callBridge<T>(
  command: string,
  payload: Record<string, unknown> = {}
): Promise<BridgeResponse<T>> {
  const python = process.env.CONTRACT_AGENT_PYTHON || 'python';
  const args = [
    '-m',
    'contract_agent.interfaces.console_bridge',
    command,
    '--payload-json',
    JSON.stringify(payload)
  ];
  const config = process.env.CONTRACT_AGENT_CONFIG;
  if (config) {
    args.push('--config', config);
  }

  try {
    const {stdout} = await execFileAsync(python, args, {
      cwd: process.env.CONTRACT_AGENT_ROOT || process.cwd(),
      windowsHide: true
    });
    return JSON.parse(stdout) as BridgeResponse<T>;
  } catch (error) {
    return bridgeErrorFromExecFailure(error);
  }
}

export function bridgeErrorFromExecFailure(error: unknown): BridgeResponse<never> {
  const stdout = outputField(error, 'stdout');
  if (typeof stdout === 'string' && stdout.trim()) {
    const bridgeJson = extractBridgeJson(stdout);
    if (bridgeJson) {
      const parsed = bridgeJson as BridgeResponse<never>;
      if (parsed && parsed.ok === false && parsed.error?.message) {
        return parsed;
      }
    }
  }
  const stderr = outputField(error, 'stderr');
  const message = error instanceof Error ? error.message : String(error);
  const combinedOutput = [stdout, stderr, message].filter(Boolean).join('\n').toLowerCase();
  if (isPdfOcrMemoryFailure(combinedOutput)) {
    return {
      ok: false,
      error: {
        code: 'pdf_ocr_memory_exhausted',
        message: pdfOcrMemoryGuidance()
      }
    };
  }
  return {
    ok: false,
    error: {
      code: 'bridge_unavailable',
      message: `Python bridge 不可用：${message}`
    }
  };
}

function outputField(error: unknown, field: 'stdout' | 'stderr'): string {
  if (typeof error === 'object' && error !== null && field in error) {
    const value = error[field as keyof typeof error];
    return typeof value === 'string' ? value : String(value ?? '');
  }
  return '';
}

function isPdfOcrMemoryFailure(output: string): boolean {
  return (
    (output.includes('std::bad_alloc') ||
      output.includes('bad allocation') ||
      output.includes('onnxruntime')) &&
    (output.includes('rapidocr') ||
      output.includes('ocr') ||
      output.includes('docling') ||
      output.includes('onnxruntime') ||
      output.includes('stage preprocess'))
  );
}

function pdfOcrMemoryGuidance(): string {
  return [
    'PDF OCR 内存不足，当前文件在 Docling/RapidOCR 解析时耗尽内存。',
    'PowerShell 可先关闭 OCR 后重试：',
    '$env:PARSER_DOCLING_ENABLE_OCR="false"',
    '$env:PARSER_DOCLING_FORCE_FULL_PAGE_OCR="false"',
    '然后重新运行 contract-agent console，或把 PDF 拆分成较小文件后再审查。'
  ].join('\n');
}

function extractBridgeJson(stdout: string): unknown | null {
  const lines = stdout
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (!line.startsWith('{')) {
      continue;
    }
    try {
      return JSON.parse(line);
    } catch {
      continue;
    }
  }
  try {
    return JSON.parse(stdout);
  } catch {
    return null;
  }
}
