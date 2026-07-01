import {describe, expect, test} from 'vitest';

import {
  completeCommandInput,
  commandSuggestionsForInput,
  isBuiltInCommand,
  moveCommandSelection,
  parseConsoleInput,
  unknownCommandText
} from '../src/commands.js';

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

  test('treats bare slash as help instead of crashing', () => {
    expect(parseConsoleInput('/')).toEqual({
      kind: 'command',
      name: 'help',
      args: []
    });
    expect(parseConsoleInput('/   ')).toEqual({
      kind: 'command',
      name: 'help',
      args: []
    });
  });

  test('identifies unknown slash commands without calling the Python bridge', () => {
    expect(isBuiltInCommand('review')).toBe(true);
    expect(isBuiltInCommand('initconfig')).toBe(true);
    expect(isBuiltInCommand('does-not-exist')).toBe(false);
    expect(unknownCommandText('does-not-exist')).toContain('/help');
  });

  test('lists command suggestions with descriptions after slash input', () => {
    const suggestions = commandSuggestionsForInput('/');

    expect(suggestions.length).toBeGreaterThan(0);
    expect(suggestions[0]).toMatchObject({
      name: '/help',
      description: '查看帮助'
    });
    expect(suggestions.map(item => item.name)).toContain('/review');
    expect(suggestions).toContainEqual({
      name: '/initconfig',
      description: '重新初始化模型配置'
    });
  });

  test('filters command suggestions while typing command names', () => {
    expect(commandSuggestionsForInput('/co').map(item => item.name)).toEqual(['/config']);
    expect(commandSuggestionsForInput('/review ./contract.pdf')).toEqual([]);
    expect(commandSuggestionsForInput('hello /co')).toEqual([]);
  });

  test('moves command selection with wraparound', () => {
    const suggestions = commandSuggestionsForInput('/');

    expect(moveCommandSelection(0, suggestions, 1)).toBe(1);
    expect(moveCommandSelection(0, suggestions, -1)).toBe(suggestions.length - 1);
    expect(moveCommandSelection(suggestions.length - 1, suggestions, 1)).toBe(0);
  });

  test('completes selected command and leaves a trailing space', () => {
    const suggestions = commandSuggestionsForInput('/');

    expect(completeCommandInput('/', suggestions, 0)).toBe('/help ');
    expect(completeCommandInput('/co', commandSuggestionsForInput('/co'), 0)).toBe('/config ');
  });
});
