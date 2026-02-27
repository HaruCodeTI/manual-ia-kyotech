import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-4">
      <div className="text-center">
        <h1 className="text-2xl font-bold tracking-tight">Kyotech AI</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Assistente inteligente de manuais Fujifilm
        </p>
      </div>
      <SignIn
        appearance={{
          elements: {
            footerAction: { display: "none" },
          },
        }}
      />
    </div>
  );
}
