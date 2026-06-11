import {
  createContext,
  useContext,
  useEffect,
  useReducer,
  type ReactNode,
} from 'react';
import { api } from '../api/client';
import type { AppConfig } from '../types';

interface AppState {
  config: AppConfig | null;
  operator: string;
  activeScenario: string;
  scenarioVersion: number;
}

type Action =
  | { type: 'SET_CONFIG'; config: AppConfig }
  | { type: 'SET_OPERATOR'; operator: string }
  | { type: 'SET_SCENARIO'; scenario: string };

const initialState: AppState = {
  config: null,
  operator: 'sre-operator',
  activeScenario: '',
  scenarioVersion: 0,
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_CONFIG':
      return { ...state, config: action.config };
    case 'SET_OPERATOR':
      return { ...state, operator: action.operator };
    case 'SET_SCENARIO':
      return {
        ...state,
        activeScenario: action.scenario,
        scenarioVersion: state.scenarioVersion + 1,
      };
    default:
      return state;
  }
}

interface AppStoreValue extends AppState {
  setOperator: (operator: string) => void;
  setScenario: (scenario: string) => void;
}

const AppStoreContext = createContext<AppStoreValue | null>(null);

export function AppStoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    api.getConfig().then((c) => dispatch({ type: 'SET_CONFIG', config: c }))
      .catch(() => undefined);
  }, []);

  const value: AppStoreValue = {
    ...state,
    setOperator: (operator) => dispatch({ type: 'SET_OPERATOR', operator }),
    setScenario: (scenario) => dispatch({ type: 'SET_SCENARIO', scenario }),
  };

  return (
    <AppStoreContext.Provider value={value}>
      {children}
    </AppStoreContext.Provider>
  );
}

export function useAppStore(): AppStoreValue {
  const ctx = useContext(AppStoreContext);
  if (!ctx) throw new Error('useAppStore must be used within AppStoreProvider');
  return ctx;
}
