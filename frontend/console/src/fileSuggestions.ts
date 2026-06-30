import {existsSync, readdirSync, statSync} from 'node:fs';
import {basename, dirname, isAbsolute, join, resolve} from 'node:path';

export type ReviewFileSuggestion = {
  displayPath: string;
  insertText: string;
  isDirectory: boolean;
};

export type SuggestionOptions = {
  roots?: string[];
  cwd?: string;
  maxDepth?: number;
  limit?: number;
};

const SUPPORTED_SUFFIXES = new Set(['.txt', '.md', '.pdf', '.docx']);

export function normalizeReviewPathInput(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  if (trimmed.startsWith('"') || trimmed.startsWith("'")) {
    return trimmed.slice(1);
  }
  return trimmed;
}

export function listReviewFileSuggestions(
  input: string,
  options: SuggestionOptions = {}
): ReviewFileSuggestion[] {
  const prefix = reviewPathPrefix(input);
  if (prefix === null) {
    return [];
  }
  const normalizedPrefix = normalizeReviewPathInput(prefix);
  const cwd = resolve(options.cwd ?? process.cwd());
  const roots = suggestionRoots(normalizedPrefix, options.roots, cwd);
  const limit = options.limit ?? 6;
  const files = roots.flatMap(root => scanSupportedFiles(root, options.maxDepth ?? 3, limit));
  return files
    .filter(file => matchesPathPrefix(file, normalizedPrefix, cwd))
    .sort(comparePath)
    .slice(0, limit)
    .map(file => ({
      displayPath: file,
      insertText: file,
      isDirectory: false
    }));
}

export function formatReviewFileGuidance(
  input: string,
  options: SuggestionOptions = {}
): string {
  const suggestions = listReviewFileSuggestions(input, options);
  const lines = [
    '请先选择可审查的合同文件路径。',
    '用法：/review <文件路径>。路径包含空格时请加双引号；输入 /review 后可按 Tab 补全第一项。',
  ];
  if (suggestions.length === 0) {
    lines.push('当前目录和 Downloads 暂未找到 .txt/.md/.pdf/.docx 文件。');
    return lines.join('\n');
  }
  lines.push('当前可审查文件：');
  lines.push(...suggestions.map(suggestion => `- ${suggestion.displayPath}`));
  return lines.join('\n');
}

export function completeReviewInput(
  input: string,
  suggestions: ReviewFileSuggestion[]
): string | null {
  const suggestion = suggestions[0];
  if (!suggestion) {
    return null;
  }
  return `/review ${quotePathForCommand(suggestion.insertText)}`;
}

export function quotePathForCommand(path: string): string {
  return /\s/.test(path) ? `"${path.replaceAll('"', '\\"')}"` : path;
}

function reviewPathPrefix(input: string): string | null {
  const trimmed = input.trimStart();
  if (!trimmed.toLowerCase().startsWith('/review')) {
    return null;
  }
  return trimmed.slice('/review'.length).trimStart();
}

function suggestionRoots(prefix: string, configuredRoots: string[] | undefined, cwd: string): string[] {
  if (configuredRoots?.length) {
    return configuredRoots.map(root => resolve(root)).filter(root => existsSync(root));
  }
  if (!prefix) {
    return [cwd, downloadsDir()].filter((root): root is string => Boolean(root));
  }
  const absolutePrefix = toAbsolutePath(prefix, cwd);
  const base =
    existsSync(absolutePrefix) && statSync(absolutePrefix).isDirectory()
      ? absolutePrefix
      : dirname(absolutePrefix);
  return existsSync(base) ? [resolve(base)] : [cwd];
}

function matchesPathPrefix(file: string, prefix: string, cwd: string): boolean {
  if (!prefix) {
    return true;
  }
  const absolutePrefix = toAbsolutePath(prefix, cwd);
  return lowerPath(resolve(file)).startsWith(lowerPath(resolve(absolutePrefix)));
}

function toAbsolutePath(path: string, cwd: string): string {
  return isAbsolute(path) ? path : resolve(cwd, path);
}

function lowerPath(path: string): string {
  return path.toLowerCase();
}

function scanSupportedFiles(root: string, maxDepth: number, limit: number): string[] {
  const resolvedRoot = resolve(root);
  const results: string[] = [];
  scan(resolvedRoot, maxDepth, results, limit);
  return results;
}

function scan(path: string, depth: number, results: string[], limit: number): void {
  if (depth < 0 || results.length >= limit || !existsSync(path)) {
    return;
  }
  let entries: string[];
  try {
    entries = readdirSync(path);
  } catch {
    return;
  }
  for (const entry of entries) {
    const child = join(path, entry);
    let stat;
    try {
      stat = statSync(child);
    } catch {
      continue;
    }
    if (stat.isDirectory()) {
      scan(child, depth - 1, results, limit);
      continue;
    }
    if (stat.isFile() && SUPPORTED_SUFFIXES.has(extensionOf(entry))) {
      results.push(child);
      if (results.length >= limit) {
        return;
      }
    }
  }
}

function extensionOf(path: string): string {
  const name = basename(path);
  const index = name.lastIndexOf('.');
  return index >= 0 ? name.slice(index).toLowerCase() : '';
}

function comparePath(left: string, right: string): number {
  if (left < right) {
    return -1;
  }
  if (left > right) {
    return 1;
  }
  return 0;
}

function downloadsDir(): string | null {
  const home = process.env.USERPROFILE || process.env.HOME;
  return home ? join(home, 'Downloads') : null;
}
