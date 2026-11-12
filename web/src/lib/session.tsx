"use client";

import { createContext, useContext } from "react";
import type { User } from "@/lib/api";

export const SessionContext = createContext<User | null>(null);

/** The signed-in user. Only call inside the (app) layout, which guarantees one exists. */
export function useSession(): User {
  const user = useContext(SessionContext);
  if (!user) throw new Error("useSession must be used inside the signed-in app shell");
  return user;
}
