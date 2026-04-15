import { ViewerPageClient } from "./ViewerPageClient";

interface Props {
  params: Promise<{ versionId: string }>;
  searchParams: Promise<{ page?: string }>;
}

export default async function ViewerPage({ params, searchParams }: Props) {
  const { versionId } = await params;
  const { page } = await searchParams;
  const initialPage = page ? Math.max(1, parseInt(page, 10)) : 1;

  return <ViewerPageClient versionId={versionId} initialPage={initialPage} />;
}
