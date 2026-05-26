/**
 * dateUtils.ts
 * -----------
 * Date formatting for local system/browser time.
 */

export function formatNotificationTime(timestamp: string | Date): string {
  let date: Date;
  if (typeof timestamp === 'string') {
    // Backend returns UTC timestamps without 'Z', so JS parses them as local time by mistake.
    // Append 'Z' to ensure it parses as UTC and then converts to the user's local timezone.
    const tzString = timestamp.endsWith('Z') ? timestamp : `${timestamp}Z`;
    date = new Date(tzString);
  } else {
    date = timestamp;
  }
  
  const now = new Date()
  
  // Format to local time
  const options: Intl.DateTimeFormatOptions = { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: true
  }
  
  const timeStr = date.toLocaleTimeString([], options)
  
  const isToday = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const isYesterday = date.toDateString() === yesterday.toDateString()
  
  if (isToday) {
    return timeStr
  } else if (isYesterday) {
    return `Yesterday, ${timeStr}`
  } else {
    return `${date.toLocaleDateString([], { day: '2-digit', month: 'short' })}, ${timeStr}`
  }
}
