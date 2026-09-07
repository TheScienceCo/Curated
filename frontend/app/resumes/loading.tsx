import { PageSkeleton } from "@/components/PageSkeleton";

// Scoped per route on purpose: a Suspense boundary above the dynamic
// opportunity page would commit a 200 before notFound() could set a 404.
export default function Loading() {
  return <PageSkeleton />;
}
