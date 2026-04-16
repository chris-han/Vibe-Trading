import { Suspense, lazy } from "react";
import { createBrowserRouter } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { Skeleton } from "@/components/common/Skeleton";

const Home = lazy(() => import("@/pages/Home").then(m => ({ default: m.Home })));
const Agent = lazy(() => import("@/pages/Agent").then(m => ({ default: m.Agent })));
const RunDetail = lazy(() => import("@/pages/RunDetail").then(m => ({ default: m.RunDetail })));
const Compare = lazy(() => import("@/pages/Compare").then(m => ({ default: m.Compare })));
const SessionEvents = lazy(() => import("@/pages/SessionEvents").then(m => ({ default: m.SessionEvents })));

const PageLoader = () => (
  <div className="p-8">
    <Skeleton className="h-8 w-64 mb-4" />
    <Skeleton className="h-32 w-full mb-4" />
    <Skeleton className="h-64 w-full" />
  </div>
);

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Suspense fallback={<PageLoader />}><Home /></Suspense> },
      { path: "/agent", element: <Suspense fallback={<PageLoader />}><Agent /></Suspense> },
      { path: "/session-events", element: <Suspense fallback={<PageLoader />}><SessionEvents /></Suspense> },
      { path: "/runs/:runId", element: <Suspense fallback={<PageLoader />}><RunDetail /></Suspense> },
      { path: "/compare", element: <Suspense fallback={<PageLoader />}><Compare /></Suspense> },
    ],
  },
]);
