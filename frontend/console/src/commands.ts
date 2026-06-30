export type ParsedConsoleInput =
  | {kind: 'empty'}
  | {kind: 'chat'; message: string}
  | {kind: 'command'; name: string; args: string[]};

export const BUILT_IN_COMMANDS = [
  '/help',
  '/status',
  '/config',
  '/review',
  '/tokens',
  '/clear',
  '/exit'
] as const;

const BUILT_IN_COMMAND_NAMES = new Set(BUILT_IN_COMMANDS.map(command => command.slice(1)));

export function parseConsoleInput(value: string): ParsedConsoleInput {
  const trimmed = value.trim();
  if (!trimmed) {
    return {kind: 'empty'};
  }
  if (!trimmed.startsWith('/')) {
    return {kind: 'chat', message: trimmed};
  }
  const [rawName, ...args] = splitCommand(trimmed.slice(1));
  return {
    kind: 'command',
    name: rawName.toLowerCase(),
    args
  };
}

export function isBuiltInCommand(name: string): boolean {
  return BUILT_IN_COMMAND_NAMES.has(name.toLowerCase());
}

export function unknownCommandText(name: string): string {
  return `未知命令：/${name}。输入 /help 查看可用命令。`;
}

function splitCommand(value: string): string[] {
  const parts: string[] = [];
  let current = '';
  let quote: '"' | "'" | null = null;
  for (const char of value) {
    if ((char === '"' || char === "'") && quote === null) {
      quote = char;
      continue;
    }
    if (quote === char) {
      quote = null;
      continue;
    }
    if (/\s/.test(char) && quote === null) {
      if (current) {
        parts.push(current);
        current = '';
      }
      continue;
    }
    current += char;
  }
  if (current) {
    parts.push(current);
  }
  return parts;
}

export function helpText(): string {
  return [
    '内置命令：',
    '/help 查看帮助',
    '/status 查看运行状态',
    '/config 查看脱敏模型配置',
    '/review <path> 审查合同文件',
    '/tokens 查看 token 估算',
    '/clear 清空当前会话',
    '/exit 退出控制台'
  ].join('\n');
}
