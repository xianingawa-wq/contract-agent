import {describe, expect, test} from 'vitest';

import {createEmptyTokenState, recordExchange} from '../src/tokenState.js';

describe('token state', () => {
  test('records latest exchange and session totals', () => {
    const state = recordExchange(createEmptyTokenState(), {
      inputTokens: 3,
      outputTokens: 5
    });

    expect(state.latest.inputTokens).toBe(3);
    expect(state.latest.outputTokens).toBe(5);
    expect(state.session.inputTokens).toBe(3);
    expect(state.session.outputTokens).toBe(5);
    expect(state.session.totalTokens).toBe(8);
  });
});
