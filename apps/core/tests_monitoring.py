from django.test import SimpleTestCase

from config.celery import app


class MonitoringScheduleTests(SimpleTestCase):
    def test_async_pipeline_heartbeat_is_scheduled_every_minute(self):
        schedule = app.conf.beat_schedule['record-async-pipeline-heartbeat-every-minute']
        self.assertEqual(schedule['task'], 'core.tasks.record_async_pipeline_heartbeat')
        self.assertEqual(str(schedule['schedule']), '<crontab: * * * * * (m/h/dM/MY/d)>')
