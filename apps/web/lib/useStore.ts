"use client";
import { useSyncExternalStore } from "react";
import type { Store, StoreState } from "@archstudio/app-core";

/** Bridges the framework-free Store (already tested in packages/app-core) into React. */
export function useStore(store: Store): StoreState {
  return useSyncExternalStore(store.subscribe, store.getState, store.getState);
}
