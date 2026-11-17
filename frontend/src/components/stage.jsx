import Icon from './icons'

/**
 * One colour language for where a video stands, shared by Episodes and Schedule.
 * production → review → scheduled → uploading → upcoming → live   (+ failed / rejected)
 */
export const STAGES = {
  production: { label: 'In production', short: 'Making', icon: 'film', hint: 'Being written or rendered' },
  review: { label: 'Needs review', short: 'Review', icon: 'eye', hint: 'Waiting for you to approve or reject' },
  scheduled: { label: 'Scheduled', short: 'Scheduled', icon: 'calendar', hint: 'Approved. Uploads by itself up to 12 h before its time' },
  uploading: { label: 'Uploading', short: 'Uploading', icon: 'refresh', hint: 'Being sent to YouTube right now' },
  upcoming: { label: 'On YouTube · going live', short: 'Upcoming', icon: 'clock', hint: 'Uploaded and private; YouTube makes it public at its time' },
  live: { label: 'Live on YouTube', short: 'Live', icon: 'checkCircle', hint: 'Public now' },
  failed: { label: 'Needs attention', short: 'Failed', icon: 'alertCircle', hint: 'Something went wrong; open it to retry' },
  rejected: { label: 'Rejected', short: 'Rejected', icon: 'ban', hint: 'Not going to be published' },
}

const PRODUCTION = new Set(['planned', 'writing', 'scripted', 'rendering'])

/** Stage of an episode row from /api/episodes. */
export function stageOf(e, now = Date.now()) {
  const s = e?.status
  if (PRODUCTION.has(s)) return 'production'
  if (s === 'approved') return 'scheduled'
  if (s === 'publishing') return 'uploading'
  if (s === 'published') return e.published_at && new Date(e.published_at).getTime() > now ? 'upcoming' : 'live'
  if (s === 'review' || s === 'failed' || s === 'rejected') return s
  return 'production'
}

/** Stage of a /api/calendar item (the server works out the state from YouTube's real status). */
export const stageOfSlot = (state) => ({ live: 'live', uploaded: 'upcoming', uploading: 'uploading', waiting: 'scheduled', late: 'failed' }[state] || 'scheduled')

/** When the episode goes / went live, for anything past review. */
export const goLiveAt = (e) => (e.status === 'published' ? e.published_at || e.publish_at : e.publish_at)

export function StageChip({ stage, label, solid }) {
  const s = STAGES[stage] || STAGES.production
  return (
    <span className={`stage-chip st-${stage} ${solid ? 'solid' : ''}`} title={s.hint}>
      <Icon name={s.icon} size={12} />{label || s.short}
    </span>
  )
}
