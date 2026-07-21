import Image from "next/image";
import { redirect } from "next/navigation";
import { LoginForm } from "./login-form";
import { getSession } from "@/lib/auth/session";

export const metadata = { title: "Sign in" };

export default async function LoginPage() {
  if (await getSession()) redirect("/dashboard");
  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[#111a1f] text-white">
      <Image
        src="/cyber-operations-login.png"
        alt="Cyber Legends operations room overlooking a futuristic arena"
        fill
        priority
        sizes="100vw"
        className="object-cover object-center"
      />
      <div className="absolute inset-0 bg-black/45" aria-hidden="true" />
      <div className="technical-grid absolute inset-0" aria-hidden="true" />
      <div className="relative z-10 grid min-h-[100dvh] lg:grid-cols-[minmax(360px,520px)_1fr]">
        <section className="flex items-center bg-[#111a1f]/92 px-5 py-10 sm:px-10 lg:px-14">
          <div className="w-full max-w-md">
            <div className="mb-10 flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-md bg-[#0f8d99] font-mono text-sm font-bold">CL</span>
              <div>
                <p className="font-semibold">Cyber Legends</p>
                <p className="text-sm text-white/55">AI Operations Workspace</p>
              </div>
            </div>
            <h1 className="text-3xl font-semibold leading-tight sm:text-4xl">Human control for applied AI work.</h1>
            <p className="mt-3 max-w-sm text-sm leading-6 text-white/65">
              Run workflows, review decisions, and measure impact from one operational workspace.
            </p>
            <LoginForm />
          </div>
        </section>
        <div className="hidden items-end justify-end p-10 lg:flex">
          <p className="max-w-sm text-right text-sm leading-6 text-white/62">
            Campaign intelligence, media review, prompt governance, and production operations.
          </p>
        </div>
      </div>
    </main>
  );
}
