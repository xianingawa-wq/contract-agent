export type TokenBucket = {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
};

export type TokenState = {
  currentInputTokens: number;
  latest: TokenBucket;
  session: TokenBucket;
};

export type TokenExchange = {
  inputTokens: number;
  outputTokens: number;
};

export function createEmptyTokenState(): TokenState {
  return {
    currentInputTokens: 0,
    latest: emptyBucket(),
    session: emptyBucket()
  };
}

export function withCurrentInputTokens(state: TokenState, currentInputTokens: number): TokenState {
  return {
    ...state,
    currentInputTokens
  };
}

export function recordExchange(state: TokenState, exchange: TokenExchange): TokenState {
  const latest = bucket(exchange.inputTokens, exchange.outputTokens);
  return {
    currentInputTokens: state.currentInputTokens,
    latest,
    session: bucket(
      state.session.inputTokens + exchange.inputTokens,
      state.session.outputTokens + exchange.outputTokens
    )
  };
}

function emptyBucket(): TokenBucket {
  return bucket(0, 0);
}

function bucket(inputTokens: number, outputTokens: number): TokenBucket {
  return {
    inputTokens,
    outputTokens,
    totalTokens: inputTokens + outputTokens
  };
}
