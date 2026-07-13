from routes import appCoordinator

class FakeCursor:
    def execute(self, *args, **kwargs):
        return None
    def fetchall(self):
        return []
    def fetchone(self):
        return None

cursor = FakeCursor()
appCoordinator._evaluation_committee_setup_for_item = lambda cursor, course_scope, reference_id: {
    'ok': True,
    'reader_ids': [101],
    'supervisor_id': 202,
    'member_ids': [303, 404],
    'reader_component': 'intro_report_reader',
    'supervisor_component': 'intro_supervisor',
    'committee_component': 'intro_discussion_member',
}
appCoordinator._evaluation_insert_task = lambda *args, **kwargs: True
appCoordinator._evaluation_current_coordinator_faculty_id = lambda cursor: None
result = appCoordinator._evaluation_autocreate_tasks(cursor, 'introduction', 1, created_by=7)
print('created_ids', sorted(result))
