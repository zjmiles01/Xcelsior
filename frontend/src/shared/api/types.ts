// Friendly aliases over the generated OpenAPI types (schema.d.ts).
// This is the only file allowed to reach into components['schemas'] —
// features import from here, so a regenerated contract propagates through
// one import surface and the compiler reports every affected call site.

import type { components } from './schema'

export type AnalysisResponse = components['schemas']['AnalysisResponse']
export type CategoryStats = components['schemas']['CategoryStats']
export type TechnologyStat = components['schemas']['TechnologyStat']
export type DistributionBucket = components['schemas']['DistributionBucket']
export type MetaResponse = components['schemas']['MetaResponse']

export type JobListResponse = components['schemas']['JobListResponse']
export type JobListItem = components['schemas']['JobListItem']
export type JobDetail = components['schemas']['JobDetail']
export type JobTechnology = components['schemas']['JobTechnologyOut']
export type JobLocation = components['schemas']['JobLocationOut']

export type ApiJobFilters = components['schemas']['JobFilters']
export type FacetBucket = components['schemas']['FacetBucket']
export type SearchFacets = components['schemas']['SearchFacets']
export type RelaxationOption = components['schemas']['RelaxationOption']

export type SkillDetailResponse = components['schemas']['SkillDetailResponse']
export type CoOccurrenceStat = components['schemas']['CoOccurrenceStat']
export type SkillTrend = components['schemas']['SkillTrend']

export type ProfileDetail = components['schemas']['ProfileDetail']
export type ProfileListResponse = components['schemas']['ProfileListResponse']
export type ProfileListItem = components['schemas']['ProfileListItem']
export type ProfileUpdate = components['schemas']['ProfileUpdate']
export type ProfileSkill = components['schemas']['SkillOut']
export type ProfileExperience = components['schemas']['ExperienceOut']
export type ProfileEducation = components['schemas']['EducationOut']

// Accounts + saved jobs (M10)
export type UserOut = components['schemas']['UserOut']
export type SavedJobsResponse = components['schemas']['SavedJobsResponse']
export type SavedJobOut = components['schemas']['SavedJobOut']
export type SavedJobMatch = components['schemas']['SavedJobMatch']
export type SavedJobIdsResponse = components['schemas']['SavedJobIdsResponse']

// Job matching (M9)
export type ProfileMatchesResponse = components['schemas']['ProfileMatchesResponse']
export type JobMatch = components['schemas']['JobMatchOut']
export type ScoreComponent = components['schemas']['ScoreComponentOut']
export type MatchSkill = components['schemas']['MatchSkillOut']
export type MatchJobSummary = components['schemas']['MatchJobSummary']
export type MatchProfileSummary = components['schemas']['MatchProfileSummary']
export type MatchWeights = components['schemas']['MatchWeights']
export type TitleAlignment = components['schemas']['TitleAlignmentOut']
export type ExperienceAlignment = components['schemas']['ExperienceAlignmentOut']
