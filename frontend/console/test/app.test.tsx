import React from 'react';
import {renderToString} from 'ink';
import {describe, expect, test, vi} from 'vitest';

import {AppFrame, formatCommandError, initConfigGuidance, runCommand} from '../src/App.js';
import * as bridge from '../src/bridge.js';
import {createEmptyTokenState} from '../src/tokenState.js';

describe('AppFrame', () => {
  test('renders conversation, commands and token panel', () => {
    const output = renderToString(
      <AppFrame
        messages={[
          {id: '1', role: 'system', text: '控制台已启动'},
          {id: '2', role: 'agent', text: '演示回复'}
        ]}
        input=""
        tokenState={createEmptyTokenState()}
        statusText="模型 qwen-max"
        loading={false}
        suggestions={[]}
        commandSuggestions={[]}
        selectedCommandIndex={0}
      />,
      {columns: 100}
    );

    expect(output).toContain('Contract Agent Console');
    expect(output).toContain('/help /status /config /review /tokens /initconfig /clear /exit');
    expect(output).toContain('控制台已启动');
    expect(output).toContain('Token 估算');
  });

  test('renders review path suggestions', () => {
    const output = renderToString(
      <AppFrame
        messages={[]}
        input="/review C:\\Users"
        tokenState={createEmptyTokenState()}
        statusText="本地会话"
        loading={false}
        suggestions={[
          {
            displayPath: 'C:\\Users\\16040\\Downloads\\contract.pdf',
            insertText: 'C:\\Users\\16040\\Downloads\\contract.pdf',
            isDirectory: false
          }
        ]}
        commandSuggestions={[]}
        selectedCommandIndex={0}
      />,
      {columns: 100}
    );

    expect(output).toContain('可审查文件');
    expect(output).toContain('Tab 补全');
    expect(output).toContain('contract.pdf');
  });

  test('renders command guidance in the message area', () => {
    const output = renderToString(
      <AppFrame
        messages={[
          {
            id: '1',
            role: 'error',
            text: '文件不存在：missing.pdf\n用法：/review <文件路径>。输入 /review 后可按 Tab 补全第一项。'
          }
        ]}
        input="/review missing.pdf"
        tokenState={createEmptyTokenState()}
        statusText="本地会话"
        loading={false}
        suggestions={[]}
        commandSuggestions={[]}
        selectedCommandIndex={0}
      />,
      {columns: 100}
    );

    expect(output).toContain('文件不存在');
    expect(output).toContain('Tab 补全');
  });

  test('keeps OCR retry guidance focused on parser settings', () => {
    const output = formatCommandError(
      'review',
      'pdf_ocr_memory_exhausted',
      'PDF OCR 内存不足。$env:PARSER_DOCLING_ENABLE_OCR="false"'
    );

    expect(output).toContain('PARSER_DOCLING_ENABLE_OCR');
    expect(output).not.toContain('请选择可审查的合同文件路径');
  });

  test('formats initconfig guidance for the React console', () => {
    const output = initConfigGuidance();

    expect(output).toContain('/initconfig');
    expect(output).toContain('contract-agent initconfig');
    expect(output).not.toContain('contract-agent console --initconfig');
  });

  test('renders command suggestions with descriptions and selected marker', () => {
    const output = renderToString(
      <AppFrame
        messages={[]}
        input="/"
        tokenState={createEmptyTokenState()}
        statusText="本地会话"
        loading={false}
        suggestions={[]}
        commandSuggestions={[
          {name: '/help', description: '查看帮助'},
          {name: '/review', description: '审查合同文件'}
        ]}
        selectedCommandIndex={1}
      />,
      {columns: 100}
    );

    expect(output).toContain('可用命令');
    expect(output).toContain('/help');
    expect(output).toContain('查看帮助');
    expect(output).toContain('› /review');
    expect(output).toContain('审查合同文件');
  });
});

describe('runCommand', () => {
  test('runs initconfig in the foreground terminal instead of printing exit guidance', async () => {
    const messages: string[] = [];
    const setMessages = vi.fn(updater => {
      const next = updater(messages.map((text, index) => ({id: String(index), role: 'command', text})));
      messages.splice(0, messages.length, ...next.map(item => item.text));
    });
    const suspendTerminal = vi.fn(async callback => {
      await callback();
    });
    const initConfig = vi.spyOn(bridge, 'runForegroundInitConfig').mockResolvedValue({
      ok: true,
      data: {exitCode: 0}
    });

    await runCommand('initconfig', [], {
      exit: vi.fn(),
      suspendTerminal,
      setInput: vi.fn(),
      setLoading: vi.fn(),
      setMessages,
      setTokenState: vi.fn()
    });

    expect(suspendTerminal).toHaveBeenCalledOnce();
    expect(initConfig).toHaveBeenCalledOnce();
    expect(messages.join('\n')).toContain('配置已重新保存');
    expect(messages.join('\n')).not.toContain('contract-agent console --initconfig');

    initConfig.mockRestore();
  });
});
