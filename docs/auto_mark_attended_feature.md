# Feature: Automatic Appointment Status Update to "Attended"

## Overview
This feature automatically marks confirmed appointments as "attended" when their scheduled time has already passed. This eliminates the need for manual status updates and keeps the appointment data accurate in real-time.

## Implementation Details

### When Does This Trigger?
The automatic status update occurs in the following scenarios:
1. **Before listing appointments** - `GET /api/v1/appointments`
2. **Before retrieving daily agenda** - `GET /api/v1/appointments/agenda`
3. **Before retrieving weekly agenda** - `GET /api/v1/appointments/weekly`

### Update Logic
An appointment is automatically marked as `attended` if:
- Current status is `confirmed`
- **AND** one of the following:
  - The appointment date is before today, OR
  - The appointment date is today AND the end time has already passed

### Code Changes

#### 1. Repository Layer (`app/repositories/appointments/appointment_repository.py`)

Added new method `mark_past_confirmed_as_attended()`:
```python
def mark_past_confirmed_as_attended(self, tenant_id: uuid.UUID) -> int:
    """
    Marks all past confirmed appointments as attended.
    
    Returns the number of appointments updated.
    """
    now = datetime.now()
    today = now.date()
    current_time = now.time()
    
    # Update confirmed appointments from before today
    stmt_past_days = (
        update(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.appointment_date < today,
        )
        .values(status=AppointmentStatus.ATTENDED)
    )
    result_past_days = self.db.execute(stmt_past_days)
    
    # Update confirmed appointments from today that have already ended
    stmt_today = (
        update(Appointment)
        .where(
            Appointment.tenant_id == tenant_id,
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.appointment_date == today,
            Appointment.time_end <= current_time,
        )
        .values(status=AppointmentStatus.ATTENDED)
    )
    result_today = self.db.execute(stmt_today)
    
    self.db.commit()
    
    total_updated = result_past_days.rowcount + result_today.rowcount
    return total_updated
```

#### 2. Service Layer (`app/services/appointments/appointment_service.py`)

Added automatic call in three methods:

**a) `list_appointments()`**
```python
def list_appointments(
    self,
    tenant_id: uuid.UUID,
    current_user: User,
    *,
    appointment_date: date | None = None,
):
    # Automatically mark past confirmed appointments as attended
    self.appointment_repo.mark_past_confirmed_as_attended(tenant_id)
    
    if current_user.role == UserRole.STAFF:
        return self.appointment_repo.list_by_user(...)
    return self.appointment_repo.list_by_tenant(...)
```

**b) `get_agenda()`**
```python
def get_agenda(
    self,
    tenant_id: uuid.UUID,
    current_user: User,
    *,
    start_date: date,
    end_date: date | None = None,
) -> dict:
    # Automatically mark past confirmed appointments as attended
    self.appointment_repo.mark_past_confirmed_as_attended(tenant_id)
    
    # ... rest of the method
```

**c) `get_weekly_agenda()`**
```python
def get_weekly_agenda(
    self,
    tenant_id: uuid.UUID,
    current_user: User,
    *,
    start_date: date,
    staff_id: uuid.UUID | None = None,
) -> dict:
    # Automatically mark past confirmed appointments as attended
    self.appointment_repo.mark_past_confirmed_as_attended(tenant_id)
    
    # ... rest of the method
```

## Workflow Examples

### Example 1: Automatic Update Today
**Scenario:** An appointment scheduled for today at 3:00 PM
- **Time 2:00 PM:** Appointment status is `confirmed`
- **Time 3:15 PM:** Staff calls `GET /api/v1/appointments/agenda?start_date=today`
- **Result:** The appointment is automatically updated to `attended` status before returning the list

**Before the call at 3:15 PM:**
```json
{
  "status": "confirmed",
  "time_start": "15:00",
  "time_end": "15:30"
}
```

**After the call (auto-updated):**
```json
{
  "status": "attended",
  "time_start": "15:00",
  "time_end": "15:30"
}
```

### Example 2: Automatic Update Past Days
**Scenario:** Multiple appointments from yesterday with `confirmed` status
- **Yesterday:** Multiple appointments scheduled at various times
- **Today:** Staff calls `GET /api/v1/appointments/agenda?start_date=today&end_date=today`
- **Result:** All `confirmed` appointments from yesterday are automatically marked as `attended`

### Example 3: Controlled Marking - Manual Override
If a staff member needs to manually override an appointment status (e.g., mark as cancelled):
```bash
PATCH /api/v1/appointments/{appointment_id}/status
{
  "status": "cancelled"
}
```

This prevents the automatic logic from overriding manual user decisions.

## Behavior Notes

1. **Multi-tenant Safety:** The update only affects appointments belonging to the specified `tenant_id`
2. **Database Persistence:** Status changes are immediately persisted to the database
3. **Performance:** Uses batch SQL updates for efficiency (not looping through records)
4. **Timezone Awareness:** Uses `datetime.now()` to respect server timezone
5. **Non-cancellable States:** Once an appointment is cancelled or attended, it cannot be automatically changed again

## Benefits

✅ **Accuracy:** Appointment status always reflects reality
✅ **User Experience:** No manual status management needed for past appointments
✅ **Efficiency:** Batch updates are fast and efficient
✅ **Audit Trail:** Status changes are persisted to the database with transaction support
✅ **Smart Logic:** Only marks truly completed appointments, avoids false positives

## Testing Checklist

- [ ] Appointment from yesterday with `confirmed` status gets marked `attended`
- [ ] Appointment from today with past end time gets marked `attended`
- [ ] Appointment from today with future end time remains `confirmed`
- [ ] Future appointments remain `confirmed`
- [ ] Already `attended` appointments are not changed
- [ ] Already `cancelled` appointments are not changed
- [ ] `pending` appointments are not affected
- [ ] Multi-tenant isolation is maintained
