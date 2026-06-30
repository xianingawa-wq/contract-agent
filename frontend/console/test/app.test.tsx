import React from 'react';
import {renderToString} from 'ink';
import {describe, expect, test} from 'vitest';

import {AppFrame, formatCommandError} from '../src/App.js';
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
      />,
      {columns: 100}
    );

    expect(output).toContain('Contract Agent Console');
    expect(output).toContain('/help /status /config /review /tokens /clear /exit');
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
});
