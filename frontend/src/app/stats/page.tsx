import { StatsCards } from "@/components/dashboard/StatsCards";

export default function StatsPage() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <h1 className="mb-6 text-2xl font-bold">Estatísticas</h1>
      <StatsCards />
    </div>
  );
}
