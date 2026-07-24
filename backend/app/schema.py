"""Distilled TOMS schema, injected into the query-generation prompt so Claude
writes correct MongoDB queries. Physical collection names are authoritative —
Claude must use these exact names.
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
    "attendances",
    "trainerdailyattendances",
    "topic_tracker_entries",
    "tickets",
    "feedbackforms",
    "feedbackresponses",
    "notifications",
    "app_settings",
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
trainers (trainers): employeeId* (primary business key), name, email, phone, phoneKey (normalized 10-digit), department->departments, subjects[]->subjects, skills[] (STRING[]), experience, joiningDate, status[active|unavailable], weeklyWorkloadHours, performanceScore (0-100), scheduleTrainerCodes[] (STRING[], links to schedules.trainerCode), showInRoster (Bool)
users (users): name, email*, role[admin|manager|subject_coordinator|campus_manager|trainer], trainer->trainers, coordinatorSubjects[]->subjects, isActive, mustResetPassword

# Timetable & venues
venues (venues): name, building, floor, capacity, type[classroom|lab|auditorium|seminar_hall|other], isActive
subjects (subjects): name, code*, schools[]->schools, semester->semesters, departments[]->departments, hours, trainerEligible[]->trainers, slotCount(1-4), oifNumber, dealNumber, startDate, academicYear (STRING label), topics[] (STRING[])
schedules (schedules): trainerCode (STRING, soft link to trainers.scheduleTrainerCodes), day[Mon..Sun], startTime/endTime (STRING "HH:mm"), department (STRING), section (STRING), subjectCode (STRING), subject->subjects, slot[S1|S2|S3|S4|""], semester (STRING, default "III"), replacementFor{trainerCode,trainerName}, venue->venues, isLab, isProject

# Leave, cancellation, attendance
leaves (leaves): trainer->trainers, startDate, endDate, reason, scope[full_day|slot], status[pending|approved|rejected|cancelled], affectedSchedules[]->schedules, approvedBy->users, replacementNeeded, replacements[]{schedule->schedules, replacementTrainer->trainers, assignedAt, assignedBy}
classcancellations (classcancellations): date, scope[classes|school|all], schedules[]->schedules, school->schools, reason, createdBy->users
attendances (attendances): type[trainer|student], trainer->trainers, student->students, schedule->schedules, date, status[present|absent|late|leave|od|holiday], markedBy->users
trainerdailyattendances (trainerdailyattendances): trainer->trainers, date, attendanceType[oif|leave|leave_oif|lwo|comp_off|exit|break|week_off_oif|e_leave|holiday_oif|holiday], oifNumber, mockPrepHours, foodAllowance, punchInAt, punchInSource[manual|whatsapp], markedBy->users. UNIQUE (trainer,date).

# Topic tracker, tickets, feedback, notifications
topic_tracker_entries (topic_tracker_entries): date, schedule->schedules, trainer->trainers, subject->subjects, day, slot, trainerName, branchYearSection, roomNo, courseName, topicModulesCovered[] (STRING[]), sessionStartTime, sessionEndTime, durationHrs, allottedStudents, noPresent, attendancePercent, sessionStatus, keyObservationsFeedback (TEXT), challengesFaced (TEXT), trackerStatus[pending|closed]. UNIQUE (schedule,date).
tickets (tickets): ticketId*, type[college_issue|coordinator_issue|venue_issue|accommodation_issue|trainer_issue], description (TEXT), status[pending|solving|closed], raisedBy->users, trainer->trainers, updates[]{status,comment,updatedBy,timestamps}
feedbackforms (feedbackforms): monthKey* ("YYYY-MM"), title, description, status[draft|published], publicSlug, fields[]{id,type,label,required,options,order}, createdBy->users, publishedAt
feedbackresponses (feedbackresponses): form->feedbackforms, monthKey, answers[]{fieldId,label,value}, rating(1-5), studentName, rollNumber (soft link to students.rollNumber), comments (TEXT), trainer->trainers
notifications (notifications): recipient->users, actor->users, actorName, actorRole, action, resource, message, entityPath, readAt (null = unread)
app_settings (app_settings): key*, value (Mixed)

# Notes
- "->X" means an ObjectId reference to collection X. Fields marked STRING are plain strings, NOT refs.
- schedules link to trainers by STRING code (schedules.trainerCode in trainers.scheduleTrainerCodes), NOT by ObjectId.
- To join across collections in an aggregation, use $lookup.
- Fields marked * are unique.
"""
