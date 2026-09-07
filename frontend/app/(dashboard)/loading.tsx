import { PageSkeleton } from "@/components/PageSkeleton";

// This route group exists purely so the dashboard can have a loading skeleton
// without putting a Suspense boundary above /opportunities/[id] - one there
// would commit a 200 before notFound() could set a 404. Route groups do not
// affect the URL, so this still serves "/".
export default function Loading() {
  return <PageSkeleton rows={6} />;
}
