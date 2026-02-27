interface ClerkSession {
  getToken(): Promise<string | null>;
}

interface ClerkInstance {
  session: ClerkSession | null;
}

interface Window {
  Clerk?: ClerkInstance;
}
