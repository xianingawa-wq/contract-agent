export type ParsedConsoleInput =
  | {kind: 'empty'}
  | {kind: 'chat'; message: string}
  | {kind: 'command'; name: string; args: string[]};

export type CommandSuggestion = {
  name: string;
  description: string;
};

export const BUILT_IN_COMMANDS: CommandSuggestion[] = [
  {name: '/help', description: '查看帮助'},
  {name: '/status', description: '查看运行状态'},
  {name: '/config', description: '查看脱敏模型配置'},
  {name: '/review', description: '审查合同文件'},
  {name: '/tokens', description: '查看 token 估算'},
  {name: '/initconfig', description: '重新初始化模型配置'},
  {name: '/clear', description: '清空当前会话'},
  {name: '/exit', description: '退出控制台'}
] as const;

const BUILT_IN_COMMAND_NAMES = new Set(BUILT_IN_COMMANDS.map(command => command.name.slice(1)));

export function parseConsoleInput(value: string): ParsedConsoleInput {
  const trimmed = value.trim();
  if (!trimmed) {
    return {kind: 'empty'};
  }
  if (!trimmed.startsWith('/')) {
    return {kind: 'chat', message: trimmed};
  }
  const [rawName, ...args] = splitCommand(trimmed.slice(1));
  if (!rawName) {
    return {kind: 'command', name: 'help', args: []};
  }
  return {
    kind: 'command',
    name: rawName.toLowerCase(),
    args
  };
}

export function isBuiltInCommand(name: string): boolean {
  return BUILT_IN_COMMAND_NAMES.has(name.toLowerCase());
}

export function commandSuggestionsForInput(input: string): CommandSuggestion[] {
  const trimmedStart = input.trimStart();
  if (!trimmedStart.startsWith('/') || /\s/.test(trimmedStart.slice(1))) {
    return [];
  }
  const prefix = trimmedStart.toLowerCase();
  return BUILT_IN_COMMANDS.filter(command => command.name.startsWith(prefix));
}

export function moveCommandSelection(
  currentIndex: number,
  suggestions: CommandSuggestion[],
  delta: number
): number {
  if (suggestions.length === 0) {
    return 0;
  }
  return positiveModulo(currentIndex + delta, suggestions.length);
}

export function completeCommandInput(
  input: string,
  suggestions: CommandSuggestion[],
  selectedIndex: number
): string | null {
  if (!commandSuggestionsForInput(input).length) {
    return null;
  }
  const suggestion = suggestions[positiveModulo(selectedIndex, suggestions.length)];
  return suggestion ? `${suggestion.name} ` : null;
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
    ...BUILT_IN_COMMANDS.map(command => `${command.name}${command.name === '/review' ? ' <path>' : ''} ${command.description}`)
  ].join('\n');
}

function positiveModulo(value: number, divisor: number): number {
  return ((value % divisor) + divisor) % divisor;
}
