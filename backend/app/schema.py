"""Distilled TOMS schema, injected into the query-generation prompt so Claude
writes correct MongoDB queries. Physical collection names are authoritative —
Claude must use these exact names.

Source of truth: MBUTOMS/backend/models/*.js (Mongoose). Regenerate this file
by re-reading that folder whenever models change — do not hand-edit drift.
"""

# Physical collection names (used for validation).
COLLECTIONS = [
    "schools",
    "departments",
    "academicyears",
    "semesters",
    "sections",
    "batches",
    "classes",
    "students",
    "venues",
    "subjects",
    "trainers",
    "users",
    "schedules",
    "leaves",
    "classcancellations",
    "compoffs",
    "officialholidays",
    "attendances",
    "trainerdailyattendances",
    "trainercompliances",
    "trainer_observations",
    "trainerplpoverrides",
    "student_monthly_test_reports",
    "topic_tracker_entries",
    "tickets",
    "feedbackforms",
    "feedbackresponses",
    "notifications",
    "app_settings",
    "whatsappsyncjobs",
]

SCHEMA_TEXT = """\
Database: toms (MongoDB). All docs have createdAt/updatedAt (timestamps).
Use the EXACT physical collection names shown in parentheses.

# Academic reference trees
schools (schools): name*, code*
departments (departments): name*, code*, school->schools, description
academicyears (academicyears): name (e.g. "2025-26"), startDate, endDate, isActive
semesters (semesters): name, number, academicYear->academicyears, isActive
sections (sections): name, department->departments
batches (batches): name, section->sections, semester->semesters, studentCount
classes (classes / ClassGroup): department (STRING), section (STRING), py (Number, passing year), currentSemester (STRING), status[active|inactive]
students (students): rollNumber*, name, email, branch, section->sections, sectionLabel (STRING), semester->semesters, batch->batches, status[active|inactive|graduated]

# People & access
trainers (trainers): employeeId* (primary business key), name, email, phone, phoneKey (normalized 10-digit), department->departments, subjects[]->subjects, skills[] (STRING[]), experience, joiningDate, status[active|unavailable], weeklyWorkloadHours, performanceScore (0-100), scheduleTrainerCodes[] (STRING[], links to schedules.trainerCode), showInRoster (Bool), employmentStatus[active|resigned], resignationDate, includeInAttendanceUntilMonth (STRING "YYYY-MM"), successorTrainer->trainers, roleTransferEffectiveDate, createdAsBulkReplacement (Bool), replacementAttendanceFrom/To
users (users): name, email*, role[admin|manager|subject_coordinator|campus_manager|evaluator|trainer], trainer->trainers, coordinatorSubjects[]->subjects, evaluatorSubjects[]->subjects, sessionVersion, isActive, mustResetPassword

# Timetable & venues
venues (venues): name, building, floor, capacity, type[classroom|lab|auditorium|seminar_hall|other], isActive
subjects (subjects): name, code*, schools[]->schools, semester->semesters, departments[]->departments, allDepartments (Bool), hours, trainerEligible[]->trainers, slotCount(1-4), slotTimings{s1..s4}, oifNumber, dealNumber, startDate, academicYear (STRING label), syllabusUrl, choUrl, practicePortalUrl, topics[] (STRING[])
schedules (schedules): trainerCode (STRING, soft link to trainers.scheduleTrainerCodes), day[Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday], startTime/endTime (STRING "HH:mm"), department (STRING), section (STRING), subjectCode (STRING), subject->subjects, slot[S1|S2|S3|S4|""], semester (STRING, default "III"), replacementFor{trainerCode,trainerName}, venue->venues, isLab, isProject

# Leave, cancellation, attendance
leaves (leaves): trainer->trainers, startDate, endDate, reason, scope[full_day|slot], status[pending|approved|rejected|cancelled], affectedSchedules[]->schedules, approvedBy->users, replacementNeeded, replacements[]{schedule->schedules, replacementTrainer->trainers, isExternal, externalTrainerName, assignedAt, assignedBy->users}, bulkReplacement{groupId, fromDate, toDate, replacementTrainer->trainers, assignedAt, assignedBy->users}
classcancellations (classcancellations): date, scope[classes|school|all], schedules[]->schedules, school->schools, reason, createdBy->users
compoffs (compoffs): trainer->trainers (nullable), employeeId, name, base, dateWorkedOn, uniqueId, count, status[pending|closed], availedOn
officialholidays (officialholidays): date* (unique, one row per calendar holiday), name, createdBy->users
attendances (attendances): STUDENT attendance records — type[trainer|student] (in practice always "student" for querying), trainer->trainers, student->students, schedule->schedules, date, status[present|absent|late|leave|od|holiday], markedBy->users
trainerdailyattendances (trainerdailyattendances): TRAINER attendance records — trainer->trainers, date, attendanceType[oif|leave|leave_oif|lwo|comp_off|exit|break|week_off_oif|e_leave|holiday_oif|holiday], oifNumber, mockPrepHours, classHandlingHours, foodAllowance, punchInAt, punchInSource[manual|whatsapp], punchInImageUrl, punchInRawPhone, whatsappMessageIds[] (STRING[]), markedBy->users. UNIQUE (trainer,date).

# Trainer performance & compliance
trainercompliances (trainercompliances): trainer->trainers, date, dateKey (STRING "YYYY-MM-DD"), monthKey (STRING "YYYY-MM"), remark (TEXT), createdBy->users
trainer_observations (trainer_observations): trainer->trainers, monthKey (STRING "YYYY-MM"), type[demo|class], rating(0.5-5), comments (TEXT), schedule->schedules (nullable, class observations only), department/section/slot/startTime/endTime/day (STRING context), subjectCode, observationDate (STRING "YYYY-MM-DD"), observationTime (STRING "HH:MM"), ratedBy->users. UNIQUE (trainer,monthKey,type).
trainerplpoverrides (trainerplpoverrides): trainer->trainers, cycleKey (STRING "YYYY-MM"), finalRating(0-4.5), updatedBy->users. UNIQUE (trainer,cycleKey).

# Student assessment
student_monthly_test_reports (student_monthly_test_reports): month (STRING "YYYY-MM"), student->students, subject->subjects, subjectCode, subjectName, department (STRING), section (STRING), py, semester (STRING), marksObtained, maxMarks, attendance[P|A], remarks, enteredBy->users. UNIQUE (month,student,subject).

# Topic tracker, tickets, feedback, notifications
topic_tracker_entries (topic_tracker_entries): date, schedule->schedules, trainer->trainers, subject->subjects, day, slot, trainerName, branchYearSection, roomNo, courseName, topicModulesCovered[] (STRING[]), sessionStartTime, sessionEndTime, durationHrs, allottedStudents, noPresent, attendancePercent, sessionStatus, keyObservationsFeedback (TEXT), challengesFaced (TEXT), trackerStatus[pending|closed], cancellationApprovalStatus[none|pending|approved|rejected], cancellationApprovedBy->users, classCancellation->classcancellations, closedBy->users, markedBy->users. UNIQUE (schedule,date).
tickets (tickets): ticketId*, type[college_issue|coordinator_issue|venue_issue|accommodation_issue|trainer_issue], description (TEXT), status[pending|solving|closed], raisedBy->users, trainer->trainers, updates[]{status,comment,updatedBy,timestamps}
feedbackforms (feedbackforms): monthKey* ("YYYY-MM"), title, description, status[draft|published], publicSlug*, fields[]{id,type,label,required,options,order}, createdBy->users, publishedAt
feedbackresponses (feedbackresponses): form->feedbackforms, monthKey, answers[]{fieldId,label,value}, rating(1-5), studentName, rollNumber (soft link to students.rollNumber), comments (TEXT), trainer->trainers
notifications (notifications): recipient->users, actor->users, actorName, actorRole, action, resource, message, entityPath, readAt (null = unread)

# System
app_settings (app_settings): key*, value (Mixed)
whatsappsyncjobs (whatsappsyncjobs): lookbackHours, force (Bool), status[pending|running|completed|failed], requestedBy->users, claimedAt, completedAt, result (Mixed), error

# Indexes — prefer these fields for $match/$sort, and always $match on an
# indexed field BEFORE any $lookup that joins into the collection below.
# "unique" combos double as the natural key for that collection.
attendances: {type,date,trainer} | {type,date,student} | {date,status}
batches: {section,semester,name} unique
classcancellations: {date} | {date,schedules} | {createdAt desc}
classes: {department,section,currentSemester} unique | {status,department,section,currentSemester}
compoffs: {employeeId,status,dateWorkedOn} | {trainer,status,dateWorkedOn} | {trainer,availedOn,status} | {uniqueId}
departments: {name} unique | {code} unique
feedbackforms: {monthKey} unique | {publicSlug} unique-sparse | {status,monthKey desc}
feedbackresponses: {form,createdAt desc} | {monthKey,createdAt desc} | {trainer,monthKey}
leaves: {status,startDate,endDate} | {trainer,status,startDate,endDate} | {affectedSchedules} | {replacements.replacementTrainer,status,startDate,endDate} | {replacements.schedule,status,startDate,endDate}
notifications: {recipient} | {recipient,readAt,createdAt desc}
officialholidays: {date} unique
schedules: {trainerCode} | {trainerCode,day,startTime} | {day,startTime} | {day,subject,startTime} | {department,section,semester} | {semester,trainerCode}
schools: {name} unique | {code} unique
sections: {department,name} unique
semesters: {academicYear,number} unique
students: {rollNumber} unique | {status,branch,sectionLabel} | {status,py,semesterLabel} | {status,branch,sectionLabel,semesterLabel,rollNumber}
student_monthly_test_reports: {month,student,subject} unique | {month,department,section,semester,subject} | {month,subject}
subjects: {code} unique | {trainerEligible}
tickets: {ticketId} unique | {status,createdAt desc} | {raisedBy,createdAt desc} | {trainer,createdAt desc}
topic_tracker_entries: {schedule,date} unique | {date} | {trackerStatus} | {cancellationApprovalStatus} | {subject,date,trackerStatus} | {trainer,date} | {subject,trackerStatus,date} | {trainer,trackerStatus,date} | {sessionStatus,cancellationApprovalStatus,date desc}
trainercompliances: {trainer} | {monthKey} | {trainer,monthKey} | {monthKey,createdAt desc}
trainerdailyattendances: {trainer,date} unique | {date} | {punchInAt desc} | {trainer,punchInAt desc} | {whatsappMessageIds}
trainer_observations: {trainer,monthKey,type} unique | {monthKey,type}
trainerplpoverrides: {trainer} | {cycleKey} | {trainer,cycleKey} unique
trainers: {employeeId} unique | {email} unique-sparse | {department,name} | {subjects} | {scheduleTrainerCodes} | {phoneKey} | {employmentStatus,includeInAttendanceUntilMonth} | {createdAsBulkReplacement,replacementAttendanceFrom,replacementAttendanceTo}
users: {email} unique | {role,trainer}
venues: {name,building} unique
whatsappsyncjobs: {status,createdAt}

# Notes
- All Date-typed fields (date, startDate, endDate, approvedAt, assignedAt,
  fromDate, toDate, readAt, publishedAt, dateWorkedOn, availedOn,
  cancellationApprovedAt, closedAt, joiningDate, resignationDate,
  roleTransferEffectiveDate, replacementAttendanceFrom,
  replacementAttendanceTo, punchInAt, claimedAt, completedAt, createdAt,
  updatedAt) are stored as BSON Date, not strings. Emit plain ISO-8601
  strings for them (e.g. "2026-08-01" or "2026-08-01T00:00:00") in $match/
  $gte/$lte/$in — the backend converts these to real Date objects before
  running the query, so do not wrap them in $dateFromString yourself.
- Attendance routing is by WHO, not by keyword match: a question about a
  TRAINER's attendance (present/absent/leave/OIF/punch-in etc.) must query
  trainerdailyattendances. A question about a STUDENT's attendance must
  query attendances. Do not use attendances for trainers just because it has
  a type:"trainer" enum value, and do not use trainerdailyattendances for
  students — trainerdailyattendances has no student field at all.
- schedules vs topic_tracker_entries is a PLAN vs ACTUAL distinction, NOT a
  date-range one — do not decide based on "single day" vs "range":
  - schedules is the standing weekly timetable PLAN (which trainer/
    subject/venue occupies a slot on a given weekday — no date field, no
    outcome). Use it ONLY for plan/roster/assignment wording — "who's
    scheduled/assigned to teach today", "what's on the timetable" — by
    matching schedules.day against the relevant weekday(s).
  - topic_tracker_entries is the TRACKING record of an actual session
    occurrence (one row per schedule+date, created as each session is
    held/tracked) and is the only place with the session's real-world
    status: trackerStatus (pending = not yet closed out, closed = wrapped
    up), topicModulesCovered[], attendance counts, cancellation approval.
    Use it for ANYTHING about actual occurrence — "how many classes were
    taken/held", "who took/conducted a class", attendance, topics covered,
    closed vs. pending — EVEN when scoped to a single day like "today" or
    "Monday": schedules is just the template and won't reflect
    cancellations/leaves/no-shows, so it cannot answer what actually
    happened. Filter topic_tracker_entries.date with $gte/$lte (or an
    exact match for one day), computed from the current-date context.
  - Rows are created as each session is actually held/tracked, so a
    topic_tracker_entries query for a date with nothing tracked yet
    legitimately returns zero rows — that's a correct "nothing tracked
    yet" answer, not a reason to fall back to schedules.
  - "who's taking classes today" (future-oriented roster wording) and "how
    many classes were taken today"/"who took a class" (past tense, an
    actual-occurrence fact) read almost the same but aren't — the first is
    schedules, the second is topic_tracker_entries. When a question could
    plausibly be read either way, default to topic_tracker_entries, since
    it's the ledger that also tells you whether a planned class actually
    happened.
- "->X" means an ObjectId reference to collection X. Fields marked STRING are plain strings, NOT refs.
- schedules link to trainers by STRING code (schedules.trainerCode in trainers.scheduleTrainerCodes), NOT by ObjectId.
- To join across collections in an aggregation, use $lookup, and lead with a
  $match on one of that collection's indexed fields (see # Indexes above) so
  the join only scans matching documents instead of the full collection.
- Fields marked * are unique.
- schedules.day (Monday..Sunday, full names) is a recurring weekday LABEL, not a calendar date
  — schedules has NO date field at all, since it's the standing weekly
  timetable template, not dated occurrences. Never use {"day": {"$in":
  [...]}} to simulate a MULTI-DAY calendar range ("this week"/"this
  month"/"this year"/"between X and Y") — a $in over weekday names matches
  every week and filters nothing; for those, filter on an actual date field
  instead: topic_tracker_entries.date (one row per real held session,
  ->schedule), classcancellations.date, attendances.date,
  leaves.startDate/endDate, or officialholidays.date. Compute the concrete
  start/end dates from the current-date context you're given, then use
  $gte/$lte on that real date field (join to schedules via $lookup if you
  also need timetable details like trainer/venue/subject).
  For a SINGLE specific day's roster/plan question ("today", "who's
  teaching today"), matching schedules.day against that one weekday is
  correct and is NOT the same mistake — see the schedules vs
  topic_tracker_entries note above for when to prefer schedules (full-day
  plan) over topic_tracker_entries (partial until tracked, but has real
  status/outcomes).
"""
