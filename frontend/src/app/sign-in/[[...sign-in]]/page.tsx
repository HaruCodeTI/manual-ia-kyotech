/* eslint-disable @next/next/no-img-element */
import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-[#111] px-4">
      <div className="flex flex-col items-center gap-3 text-center">
        <img
          src="/kyotech-logo.png"
          alt="Kyotech Endoscopia"
          className="h-16 w-auto object-contain"
        />
        <p className="text-sm text-neutral-400">
          Assistente inteligente de manuais Fujifilm
        </p>
      </div>
      <SignIn
        appearance={{
          elements: {
            footerAction: { display: "none" },
            card: {
              boxShadow: "0 4px 24px 0 rgb(0 0 0 / 0.3)",
              borderRadius: "0.75rem",
            },
          },
        }}
      />
    </div>
  );
}
