import { api, ApiError } from "@/lib/api";
import { ProfileEditor } from "@/components/ProfileEditor";
import type { CandidateProfile } from "@/lib/types";

export const dynamic = "force-dynamic";
export const metadata = { title: "Profile | Job Intelligence Agent" };

export default async function ProfilePage() {
  let profile: CandidateProfile | null = null;
  let error: string | null = null;

  try {
    profile = await api.profile();
  } catch (err) {
    error = err instanceof ApiError ? err.message : "Could not load the profile.";
  }

  return (
    <>
      <div className="page-header">
        <h1>Candidate profile</h1>
        <p>
          Everything scoring compares against. The compensation bands and dimension weights are
          yours to set — the defaults are a starting point, not a judgement.
        </p>
      </div>
      {error && <div className="banner banner-error">{error}</div>}
      {profile && <ProfileEditor profile={profile} />}
    </>
  );
}
