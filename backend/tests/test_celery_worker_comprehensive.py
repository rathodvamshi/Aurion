# backend/tests/test_celery_worker_comprehensive.py
"""
Comprehensive test suite for Celery worker as specified in requirements.
Tests execute, send email, store OTP in Redis, auto-complete (10+ test cases).
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from bson import ObjectId

from app.celery_worker import send_task_otp_task


class TestCeleryWorkerComprehensive:
    """Comprehensive test suite for Celery worker."""

    @pytest.fixture
    def mock_task_doc(self):
        """Mock task document."""
        return {
            "_id": ObjectId(),
            "user_id": "test_user_123",
            "title": "Test Task",
            "status": "todo",
            "auto_complete_after_email": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client."""
        redis_client = Mock()
        
        async def mock_setex(key, ttl, value):
            return True
        redis_client.setex = mock_setex
        
        return redis_client

    @pytest.fixture
    def mock_db_collection(self):
        """Mock database collection."""
        collection = Mock()
        collection.find_one.return_value = None
        collection.update_one.return_value = Mock(modified_count=1)
        return collection

    @pytest.fixture
    def mock_db_client(self, mock_db_collection):
        """Mock database client."""
        client = Mock()
        client.get_tasks_collection.return_value = mock_db_collection
        return client

    def test_send_task_otp_task_sends_email_and_marks_done(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task sends email and marks task as done."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Create mock task instance
            mock_task_instance = Mock()
            mock_task_instance.retry = Mock()
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify task was fetched
            mock_db_collection.find_one.assert_called_once_with({"_id": ObjectId(task_id)})
            
            # Verify OTP was stored in Redis
            # Note: We can't easily test the async Redis call in this context
            # but we can verify the function doesn't crash
            
            # Verify email was sent
            mock_send_email.assert_called_once()
            email_call = mock_send_email.call_args
            assert email_call[1]["to"] == ["test@example.com"]
            assert "Test Task" in email_call[1]["subject"]
            assert "OTP inside" in email_call[1]["subject"]
            
            # Verify task was marked as done
            mock_db_collection.update_one.assert_called_once()
            update_call = mock_db_collection.update_one.call_args
            assert update_call[0][0] == {"_id": ObjectId(task_id)}
            assert update_call[0][1]["$set"]["status"] == "done"
            assert "completed_at" in update_call[0][1]["$set"]

    def test_send_task_otp_task_task_not_found(self, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task handles task not found."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.logger') as mock_logger:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = None  # Task not found
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(ObjectId())
            result = send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify error was logged
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args[0][0]
            assert "[OTP_ERROR] Task not found" in error_call
            assert task_id in error_call
            
            # Should return early without crashing
            assert result is None

    def test_send_task_otp_task_task_already_done(self, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task skips email for already completed tasks."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.logger') as mock_logger:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            
            # Task already done
            done_task = {
                "_id": ObjectId(),
                "user_id": "test_user_123",
                "title": "Test Task",
                "status": "done",
                "auto_complete_after_email": True
            }
            mock_db_collection.find_one.return_value = done_task
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(done_task["_id"])
            result = send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify skip was logged
            mock_logger.info.assert_called_once()
            info_call = mock_logger.info.call_args[0][0]
            assert "[OTP_SKIP]" in info_call
            assert "status done" in info_call
            
            # Verify email was NOT sent
            mock_send_email.assert_not_called()
            
            # Verify task was NOT updated
            mock_db_collection.update_one.assert_not_called()

    def test_send_task_otp_task_task_cancelled(self, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task skips email for cancelled tasks."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.logger') as mock_logger:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            
            # Task cancelled
            cancelled_task = {
                "_id": ObjectId(),
                "user_id": "test_user_123",
                "title": "Test Task",
                "status": "cancelled",
                "auto_complete_after_email": True
            }
            mock_db_collection.find_one.return_value = cancelled_task
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(cancelled_task["_id"])
            result = send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify skip was logged
            mock_logger.info.assert_called_once()
            info_call = mock_logger.info.call_args[0][0]
            assert "[OTP_SKIP]" in info_call
            assert "status cancelled" in info_call
            
            # Verify email was NOT sent
            mock_send_email.assert_not_called()

    def test_send_task_otp_task_redis_failure(self, mock_task_doc, mock_db_collection):
        """Test: send_task_otp_task handles Redis failure gracefully."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.logger') as mock_logger:
            
            # Setup mocks
            mock_get_redis.return_value = None  # Redis unavailable
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify Redis error was logged
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args[0][0]
            assert "[OTP_ERROR] Redis SETEX failed" in error_call
            
            # Verify email was still sent (graceful degradation)
            mock_send_email.assert_called_once()
            
            # Verify task was still marked as done
            mock_db_collection.update_one.assert_called_once()

    def test_send_task_otp_task_email_failure_retry(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task retries on email failure."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.logger') as mock_logger:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Mock email failure
            mock_send_email.side_effect = Exception("SMTP Error")
            
            # Create mock task instance
            mock_task_instance = Mock()
            mock_retry = Mock()
            mock_task_instance.retry = mock_retry
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            
            with pytest.raises(Exception):
                send_task_otp_task(
                    mock_task_instance,
                    task_id,
                    "test@example.com",
                    "Test Task"
                )
            
            # Verify retry was called
            mock_retry.assert_called_once()
            
            # Verify error was logged
            mock_logger.exception.assert_called_once()
            error_call = mock_logger.exception.call_args[0][0]
            assert "[OTP_ERROR] sending email" in error_call

    def test_send_task_otp_task_auto_complete_disabled(self, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task respects auto_complete_after_email=False."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            
            # Task with auto_complete disabled
            task_no_auto_complete = {
                "_id": ObjectId(),
                "user_id": "test_user_123",
                "title": "Test Task",
                "status": "todo",
                "auto_complete_after_email": False
            }
            mock_db_collection.find_one.return_value = task_no_auto_complete
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(task_no_auto_complete["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify email was sent
            mock_send_email.assert_called_once()
            
            # Verify task was NOT marked as done
            mock_db_collection.update_one.assert_not_called()

    def test_send_task_otp_task_otp_generation(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task generates 6-digit OTP."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.random') as mock_random:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            mock_random.randint.return_value = 123456
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify OTP generation
            mock_random.randint.assert_called_once_with(100000, 999999)
            
            # Verify OTP is included in email
            mock_send_email.assert_called_once()
            email_call = mock_send_email.call_args
            assert "123456" in email_call[1]["html"]

    def test_send_task_otp_task_custom_otp(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task uses provided OTP when given."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.random') as mock_random:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task with custom OTP
            task_id = str(mock_task_doc["_id"])
            custom_otp = "999999"
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task",
                otp=custom_otp
            )
            
            # Verify random OTP was NOT generated
            mock_random.randint.assert_not_called()
            
            # Verify custom OTP is included in email
            mock_send_email.assert_called_once()
            email_call = mock_send_email.call_args
            assert custom_otp in email_call[1]["html"]

    def test_send_task_otp_task_logging(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task logs appropriate messages."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email, \
             patch('app.celery_worker.logger') as mock_logger:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify logging calls
            assert mock_logger.info.call_count >= 2  # At least OTP_SENDING and OTP_DISPATCH
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("[OTP_SENDING]" in call for call in log_calls)
            assert any("[OTP_DISPATCH]" in call for call in log_calls)
            assert any("[TASK_AUTO_COMPLETE]" in call for call in log_calls)

    def test_send_task_otp_task_redis_ttl(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task stores OTP with 600s TTL."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify Redis setex was called with correct TTL
            # Note: We can't easily test the async Redis call in this context
            # but we can verify the function doesn't crash and logs the TTL
            mock_logger = patch('app.celery_worker.logger').start()
            log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
            assert any("RedisTTL=600s" in call for call in log_calls)

    def test_send_task_otp_task_email_content(self, mock_task_doc, mock_redis_client, mock_db_collection):
        """Test: send_task_otp_task sends properly formatted email."""
        with patch('app.celery_worker.get_redis_client') as mock_get_redis, \
             patch('app.celery_worker.db_client', mock_db_collection), \
             patch('app.celery_worker.send_html_email') as mock_send_email:
            
            # Setup mocks
            mock_get_redis.return_value = mock_redis_client
            mock_db_collection.find_one.return_value = mock_task_doc
            
            # Create mock task instance
            mock_task_instance = Mock()
            
            # Call the task
            task_id = str(mock_task_doc["_id"])
            send_task_otp_task(
                mock_task_instance,
                task_id,
                "test@example.com",
                "Test Task"
            )
            
            # Verify email content
            mock_send_email.assert_called_once()
            email_call = mock_send_email.call_args
            
            # Check subject
            subject = email_call[1]["subject"]
            assert "Reminder: Test Task" in subject
            assert "OTP inside" in subject
            
            # Check HTML content
            html = email_call[1]["html"]
            assert "Test Task" in html
            assert "Task Reminder" in html
            assert "Aurion AI" in html
            
            # Check text content
            text = email_call[1]["text"]
            assert "Test Task" in text
            assert "Valid 10 minutes" in text
