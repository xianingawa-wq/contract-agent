import React, {useEffect, useMemo, useState} from 'react';
import {Box, Text, useApp, useInput, type SuspendTerminal} from 'ink';

import {
  BUILT_IN_COMMANDS,
  commandSuggestionsForInput,
  completeCommandInput,
  helpText,
  isBuiltInCommand,
  moveCommandSelection,
  parseConsoleInput,
  type CommandSuggestion,
  unknownCommandText
} from './commands.js';
import {callBridge, runForegroundInitConfig, type ChatData} from './bridge.js';
import {
  completeReviewInput,
  formatReviewFileGuidance,
  listReviewFileSuggestions,
  normalizeReviewPathInput,
  type ReviewFileSuggestion
} from './fileSuggestions.js';
import {
  createEmptyTokenState,
  recordExchange,
  type TokenState,
  withCurrentInputTokens
} from './tokenState.js';

export type ConsoleMessage = {
  id: string;
  role: 'system' | 'user' | 'agent' | 'command' | 'error';
  text: string;
};

export type AppFrameProps = {
  messages: ConsoleMessage[];
  input: string;
  tokenState: TokenState;
  statusText: string;
  loading: boolean;
  suggestions: ReviewFileSuggestion[];
  commandSuggestions: CommandSuggestion[];
  selectedCommandIndex: number;
};

export function AppFrame({
  messages,
  input,
  tokenState,
  statusText,
  loading,
  suggestions,
  commandSuggestions,
  selectedCommandIndex
}: AppFrameProps): React.ReactElement {
  const commandLine = BUILT_IN_COMMANDS.map(command => command.name).join(' ');
  return (
    <Box flexDirection="column" paddingX={1}>
      <Box justifyContent="space-between">
        <Text color="cyan" bold>
          Contract Agent Console
        </Text>
        <Text color={loading ? 'yellow' : 'green'}>{loading ? '执行中' : statusText}</Text>
      </Box>
      <Text color="gray">{commandLine}</Text>
      <Box marginTop={1} flexDirection="column">
        {messages.length === 0 ? (
          <Text color="gray">暂无消息。输入内容开始对话，或输入 /help 查看命令。</Text>
        ) : (
          messages.slice(-10).map(message => (
            <Text key={message.id} color={messageColor(message.role)}>
              {messagePrefix(message.role)}
              {message.text}
            </Text>
          ))
        )}
      </Box>
      {commandSuggestions.length > 0 && (
        <Box marginTop={1} flexDirection="column">
          <Text color="yellow">可用命令</Text>
          {commandSuggestions.map((command, index) => {
            const selected = index === selectedCommandIndex;
            return (
              <Text key={command.name} color={selected ? 'cyan' : 'gray'}>
                {selected ? '›' : ' '} {command.name}  {command.description}
              </Text>
            );
          })}
        </Box>
      )}
      {suggestions.length > 0 && (
        <Box marginTop={1} flexDirection="column">
          <Text color="yellow">可审查文件（Tab 补全第一项）：</Text>
          {suggestions.map(suggestion => (
            <Text key={suggestion.displayPath} color="gray">
              {suggestion.displayPath}
            </Text>
          ))}
        </Box>
      )}
      <Box marginTop={1} borderStyle="round" borderColor="gray" flexDirection="column" paddingX={1}>
        <Text color="cyan">Token 估算</Text>
        <Text>
          当前输入 {tokenState.currentInputTokens} | 最近一轮 输入 {tokenState.latest.inputTokens} /
          输出 {tokenState.latest.outputTokens} / 合计 {tokenState.latest.totalTokens}
        </Text>
        <Text>
          会话累计 输入 {tokenState.session.inputTokens} / 输出 {tokenState.session.outputTokens} /
          合计 {tokenState.session.totalTokens}
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text color="green">你&gt; </Text>
        <Text>{input}</Text>
      </Box>
    </Box>
  );
}

export function App(): React.ReactElement {
  const {exit, suspendTerminal} = useApp();
  const [messages, setMessages] = useState<ConsoleMessage[]>([
    {id: 'welcome', role: 'system', text: '控制台已启动。输入 /help 查看内置命令。'}
  ]);
  const [input, setInput] = useState('');
  const [tokenState, setTokenState] = useState(createEmptyTokenState);
  const [loading, setLoading] = useState(false);
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0);
  const statusText = useMemo(() => '本地会话', []);
  const suggestions = useMemo(() => listReviewFileSuggestions(input), [input]);
  const commandSuggestions = useMemo(() => commandSuggestionsForInput(input), [input]);

  useEffect(() => {
    setSelectedCommandIndex(current =>
      commandSuggestions.length === 0 ? 0 : Math.min(current, commandSuggestions.length - 1)
    );
  }, [commandSuggestions.length]);

  useEffect(() => {
    const timeout = setTimeout(async () => {
      const result = await callBridge<{estimated_tokens: number}>('estimate', {text: input});
      if (result.ok) {
        setTokenState(current => withCurrentInputTokens(current, result.data.estimated_tokens));
      }
    }, 80);
    return () => clearTimeout(timeout);
  }, [input]);

  useInput((inputChar, key) => {
    if (key.tab) {
      const completed =
        completeCommandInput(input, commandSuggestions, selectedCommandIndex) ??
        completeReviewInput(input, suggestions);
      if (completed) {
        setInput(completed);
      }
      return;
    }
    if (key.upArrow && commandSuggestions.length > 0) {
      setSelectedCommandIndex(current => moveCommandSelection(current, commandSuggestions, -1));
      return;
    }
    if (key.downArrow && commandSuggestions.length > 0) {
      setSelectedCommandIndex(current => moveCommandSelection(current, commandSuggestions, 1));
      return;
    }
    if (key.return) {
      void submitInput(input, {
        exit,
        suspendTerminal,
        setInput,
        setLoading,
        setMessages,
        setTokenState
      });
      return;
    }
    if (key.backspace || key.delete) {
      setInput(current => current.slice(0, -1));
      return;
    }
    if (inputChar) {
      setInput(current => current + inputChar);
    }
  });

  return (
    <AppFrame
      messages={messages}
      input={input}
      tokenState={tokenState}
      statusText={statusText}
      loading={loading}
      suggestions={suggestions}
      commandSuggestions={commandSuggestions}
      selectedCommandIndex={selectedCommandIndex}
    />
  );
}

export type SubmitContext = {
  exit: () => void;
  suspendTerminal: SuspendTerminal;
  setInput: React.Dispatch<React.SetStateAction<string>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setMessages: React.Dispatch<React.SetStateAction<ConsoleMessage[]>>;
  setTokenState: React.Dispatch<React.SetStateAction<TokenState>>;
};

async function submitInput(value: string, context: SubmitContext): Promise<void> {
  const parsed = parseConsoleInput(value);
  if (parsed.kind === 'empty') {
    return;
  }
  context.setInput('');
  if (parsed.kind === 'chat') {
    appendMessage(context.setMessages, 'user', parsed.message);
    context.setLoading(true);
    const result = await callBridge<ChatData>('chat', {message: parsed.message});
    context.setLoading(false);
    if (!result.ok) {
      appendMessage(context.setMessages, 'error', result.error.message);
      return;
    }
    appendMessage(context.setMessages, 'agent', result.data.reply);
    context.setTokenState(current =>
      recordExchange(current, {
        inputTokens: result.data.usage.estimated_input_tokens,
        outputTokens: result.data.usage.estimated_output_tokens
      })
    );
    return;
  }
  await runCommand(parsed.name, parsed.args, context);
}

export async function runCommand(
  name: string,
  args: string[],
  context: SubmitContext
): Promise<void> {
  if (!isBuiltInCommand(name)) {
    appendMessage(context.setMessages, 'error', unknownCommandText(name));
    return;
  }
  if (name === 'exit') {
    context.exit();
    return;
  }
  if (name === 'help') {
    appendMessage(context.setMessages, 'command', helpText());
    return;
  }
  if (name === 'clear') {
    context.setMessages([]);
    context.setTokenState(createEmptyTokenState());
    return;
  }
  if (name === 'tokens') {
    appendMessage(context.setMessages, 'command', '当前 token 统计已显示在下方面板。');
    return;
  }
  if (name === 'initconfig') {
    await runInitConfigCommand(context);
    return;
  }
  if (name === 'review' && !normalizeReviewPathInput(args.join(' '))) {
    appendMessage(context.setMessages, 'command', formatReviewFileGuidance('/review '));
    return;
  }
  const bridgeCommand = name === 'review' ? 'review' : name;
  context.setLoading(true);
  const payload = name === 'review' ? {path: normalizeReviewPathInput(args.join(' '))} : {};
  const result = await callBridge<Record<string, unknown>>(bridgeCommand, payload);
  context.setLoading(false);
  if (!result.ok) {
    appendMessage(
      context.setMessages,
      'error',
      formatCommandError(name, result.error.code, result.error.message)
    );
    return;
  }
  appendMessage(context.setMessages, 'command', formatBridgeData(name, result.data));
}

async function runInitConfigCommand(context: SubmitContext): Promise<void> {
  appendMessage(context.setMessages, 'command', '开始重新初始化配置，按提示完成后会回到当前控制台。');
  context.setLoading(true);
  let result: Awaited<ReturnType<typeof runForegroundInitConfig>> | undefined;
  try {
    await context.suspendTerminal(async () => {
      result = await runForegroundInitConfig();
    });
  } catch (error) {
    result = {
      ok: false,
      error: {
        code: 'initconfig_failed',
        message: error instanceof Error ? error.message : String(error)
      }
    };
  } finally {
    context.setLoading(false);
  }

  if (!result) {
    appendMessage(context.setMessages, 'error', '配置初始化没有返回结果。');
    return;
  }
  if (!result.ok) {
    appendMessage(context.setMessages, 'error', result.error.message);
    return;
  }
  appendMessage(context.setMessages, 'command', '配置已重新保存。后续命令会读取新的本地模型配置。');
}

export function initConfigGuidance(): string {
  return [
    '输入 /initconfig 后会在当前控制台直接进入配置流程。',
    '也可以在控制台外运行：contract-agent initconfig'
  ].join('\n');
}

export function formatCommandError(command: string, code: string, message: string): string {
  if (command !== 'review') {
    return message;
  }
  if (!['missing_path', 'file_not_found', 'not_a_file'].includes(code)) {
    return message;
  }
  return `${message}\n${formatReviewFileGuidance('/review ')}`;
}

function formatBridgeData(command: string, data: Record<string, unknown>): string {
  if (command === 'status') {
    return `运行状态：${JSON.stringify(data)}`;
  }
  if (command === 'config') {
    return `模型配置：${JSON.stringify(data)}`;
  }
  if (command === 'review') {
    return [
      `合同类型：${data.contract_type ?? ''}`,
      `整体风险：${data.overall_risk ?? ''}`,
      `风险数量：${data.risk_count ?? ''}`,
      `审查概览：${data.overview ?? ''}`
    ].join('\n');
  }
  return JSON.stringify(data);
}

function appendMessage(
  setMessages: React.Dispatch<React.SetStateAction<ConsoleMessage[]>>,
  role: ConsoleMessage['role'],
  text: string
): void {
  setMessages(current => [
    ...current,
    {
      id: `${Date.now()}-${current.length}`,
      role,
      text
    }
  ]);
}

function messagePrefix(role: ConsoleMessage['role']): string {
  if (role === 'user') {
    return '你：';
  }
  if (role === 'agent') {
    return 'Agent：';
  }
  if (role === 'command') {
    return '命令：';
  }
  if (role === 'error') {
    return '错误：';
  }
  return '';
}

function messageColor(role: ConsoleMessage['role']): 'white' | 'cyan' | 'green' | 'yellow' | 'red' {
  if (role === 'agent') {
    return 'cyan';
  }
  if (role === 'command') {
    return 'green';
  }
  if (role === 'error') {
    return 'red';
  }
  if (role === 'system') {
    return 'yellow';
  }
  return 'white';
}
