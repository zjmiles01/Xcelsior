import { createBrowserRouter } from 'react-router-dom'

import { AccountPage } from '../features/account/AccountPage'
import { LoginPage, SignupPage } from '../features/auth/AuthPage'
import { RequireAuth } from '../features/auth/RequireAuth'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { HomePage } from '../features/home/HomePage'
import { JobDetailPage } from '../features/job-detail/JobDetailPage'
import { JobListPage } from '../features/job-search/JobListPage'
import { MatchesPage } from '../features/profile/MatchesPage'
import { ProfileListPage } from '../features/profile/ProfileListPage'
import { ProfileReviewPage } from '../features/profile/ProfileReviewPage'
import { SavedJobsPage } from '../features/saved/SavedJobsPage'
import { SkillDetailPage } from '../features/skill/SkillDetailPage'
import { Layout } from './Layout'

// Public routes anyone can browse (jobs, market intelligence, job details);
// the personal surface (profile, matcher, saved jobs) is wrapped in
// RequireAuth, which bounces anonymous visitors to /login and returns them
// to the action afterward (M10).
export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <HomePage /> },
      { path: '/skills', element: <DashboardPage /> },
      { path: '/jobs', element: <JobListPage /> },
      { path: '/jobs/:id', element: <JobDetailPage /> },
      { path: '/skills/:slug', element: <SkillDetailPage /> },
      { path: '/login', element: <LoginPage /> },
      { path: '/signup', element: <SignupPage /> },
      { path: '/profile', element: <RequireAuth><ProfileListPage /></RequireAuth> },
      { path: '/profile/:id', element: <RequireAuth><ProfileReviewPage /></RequireAuth> },
      {
        path: '/profile/:id/matches',
        element: <RequireAuth><MatchesPage /></RequireAuth>,
      },
      { path: '/saved', element: <RequireAuth><SavedJobsPage /></RequireAuth> },
      { path: '/account', element: <RequireAuth><AccountPage /></RequireAuth> },
    ],
  },
])
