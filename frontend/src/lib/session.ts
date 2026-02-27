"use client";

import { useUser, useAuth } from "@clerk/nextjs";

export interface AppUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

export function useAppSession() {
  const { user, isLoaded } = useUser();
  const { isSignedIn } = useAuth();

  const status = !isLoaded ? "loading" : isSignedIn ? "authenticated" : "unauthenticated";

  const appUser: AppUser | null =
    isLoaded && user
      ? {
          id: user.id,
          name: user.fullName ?? "",
          email: user.primaryEmailAddress?.emailAddress ?? "",
          role: (user.publicMetadata?.role as string) ?? "Technician",
        }
      : null;

  const isAdmin = appUser?.role === "Admin";

  return { user: appUser, status, isAdmin };
}
