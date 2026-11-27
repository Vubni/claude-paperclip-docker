import { useQuery } from "@tanstack/react-query";
import { ONBOARDING_FIRST_TASK_ORIGIN_KIND } from "@paperclipai/shared";
import { issuesApi } from "@/api/issues";
import { queryKeys } from "@/lib/queryKeys";
import { taskDisplayTitle, workspaceRussian } from "./workspaceTaskText";

export function useWorkspaceStarter(companyId: string | null) {
  const query = useQuery({
    queryKey: queryKeys.issues.onboardingFirstTask(companyId ?? "__none__"),
    queryFn: ({ signal }) => issuesApi.list(companyId!, { originKind: ONBOARDING_FIRST_TASK_ORIGIN_KIND, limit: 1 }, { signal }),
    enabled: Boolean(companyId) && workspaceRussian(),
    staleTime: 60_000,
  });
  const starter = query.data?.find(issue => issue.originKind === ONBOARDING_FIRST_TASK_ORIGIN_KIND);
  return workspaceRussian() ? starter : undefined;
}

export function starterTitle(starter: ReturnType<typeof useWorkspaceStarter>, id: string | null | undefined, title: string | null | undefined) {
  return starter && starter.id === id && title === starter.title ? taskDisplayTitle(starter) : title;
}
