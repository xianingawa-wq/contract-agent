import {describe, expect, test} from 'vitest';

import {isBuiltInCommand, parseConsoleInput, unknownCommandText} from '../src/commands.js';

describe('parseConsoleInput', () => {
  test('parses regular chat input', () => {
    expect(parseConsoleInput('请检查付款条款')).toEqual({
      kind: 'chat',
      message: '请检查付款条款'
    });
  });

  test('parses review command with path argument', () => {
    expect(parseConsoleInput('/review ./samples/contract.txt')).toEqual({
      kind: 'command',
      name: 'review',
      args: ['./samples/contract.txt']
    });
  });

  test('parses quoted review path as one argument without quotes', () => {
    expect(parseConsoleInput('/review "C:\\Users\\16040\\Downloads\\contract.pdf"')).toEqual({
      kind: 'command',
      name: 'review',
      args: ['C:\\Users\\16040\\Downloads\\contract.pdf']
    });
  });

  test('parses clear command without arguments', () => {
    expect(parseConsoleInput('/clear')).toEqual({
      kind: 'command',
      name: 'clear',
      args: []
    });
  });

  test('identifies unknown slash commands without calling the Python bridge', () => {
    expect(isBuiltInCommand('review')).toBe(true);
    expect(isBuiltInCommand('initconfig')).toBe(true);
    expect(isBuiltInCommand('does-not-exist')).toBe(false);
    expect(unknownCommandText('does-not-exist')).toContain('/help');
  });
});
