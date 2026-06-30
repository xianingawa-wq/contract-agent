import {mkdtempSync, mkdirSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

import {describe, expect, test} from 'vitest';

import {
  completeReviewInput,
  formatReviewFileGuidance,
  listReviewFileSuggestions,
  normalizeReviewPathInput,
  quotePathForCommand
} from '../src/fileSuggestions.js';

describe('review file suggestions', () => {
  test('normalizes quoted path prefixes', () => {
    expect(normalizeReviewPathInput('"C:\\Users\\16040\\Downloads\\contract.pdf"')).toBe(
      'C:\\Users\\16040\\Downloads\\contract.pdf'
    );
  });

  test('normalizes a path while the closing quote is still being typed', () => {
    expect(normalizeReviewPathInput('"C:\\Users\\16040\\Downloads')).toBe(
      'C:\\Users\\16040\\Downloads'
    );
  });

  test('lists supported contract files from the file tree', () => {
    const root = mkdtempSync(join(tmpdir(), 'contract-console-'));
    mkdirSync(join(root, 'nested'));
    writeFileSync(join(root, '采购合同.pdf'), 'pdf');
    writeFileSync(join(root, 'nested', 'draft.docx'), 'docx');
    writeFileSync(join(root, 'image.png'), 'png');

    const suggestions = listReviewFileSuggestions('/review ', {
      roots: [root],
      maxDepth: 3,
      limit: 5
    });

    expect(suggestions.map(item => item.displayPath)).toEqual([
      join(root, 'nested', 'draft.docx'),
      join(root, '采购合同.pdf')
    ]);
  });

  test('filters suggestions by typed path prefix', () => {
    const root = mkdtempSync(join(tmpdir(), 'contract-console-'));
    writeFileSync(join(root, 'contract-a.pdf'), 'pdf');
    writeFileSync(join(root, 'memo.txt'), 'txt');

    const suggestions = listReviewFileSuggestions(`/review ${join(root, 'con')}`, {
      roots: [root],
      maxDepth: 1,
      limit: 5
    });

    expect(suggestions.map(item => item.displayPath)).toEqual([join(root, 'contract-a.pdf')]);
  });

  test('filters suggestions for relative review paths', () => {
    const root = mkdtempSync(join(tmpdir(), 'contract-console-'));
    mkdirSync(join(root, 'samples'));
    writeFileSync(join(root, 'samples', 'contract-a.pdf'), 'pdf');
    writeFileSync(join(root, 'samples', 'memo.txt'), 'txt');

    const suggestions = listReviewFileSuggestions('/review ./samples/con', {
      roots: [root],
      cwd: root,
      maxDepth: 2,
      limit: 5
    });

    expect(suggestions.map(item => item.displayPath)).toEqual([
      join(root, 'samples', 'contract-a.pdf')
    ]);
  });

  test('quotes completed paths with spaces', () => {
    expect(quotePathForCommand('C:\\Users\\16040\\Downloads\\contract draft.pdf')).toBe(
      '"C:\\Users\\16040\\Downloads\\contract draft.pdf"'
    );
  });

  test('completes review input with the first suggestion', () => {
    const completed = completeReviewInput('/review C:\\Users', [
      {
        displayPath: 'C:\\Users\\16040\\Downloads\\contract draft.pdf',
        insertText: 'C:\\Users\\16040\\Downloads\\contract draft.pdf',
        isDirectory: false
      }
    ]);

    expect(completed).toBe('/review "C:\\Users\\16040\\Downloads\\contract draft.pdf"');
  });

  test('formats review guidance with file tree candidates', () => {
    const root = mkdtempSync(join(tmpdir(), 'contract-console-'));
    writeFileSync(join(root, 'candidate.pdf'), 'pdf');

    const guidance = formatReviewFileGuidance('/review ', {
      roots: [root],
      cwd: root,
      maxDepth: 1,
      limit: 5
    });

    expect(guidance).toContain('Tab');
    expect(guidance).toContain('candidate.pdf');
  });
});
