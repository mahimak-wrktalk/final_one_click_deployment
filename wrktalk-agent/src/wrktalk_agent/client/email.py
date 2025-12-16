"""SMTP email client for deployment notifications."""

import smtplib
import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

logger = structlog.get_logger()


class EmailClient:
    """SMTP email client for sending deployment notifications."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_from: str,
    ):
        """Initialize email client.

        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            smtp_user: SMTP username
            smtp_password: SMTP password
            smtp_from: From email address
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.smtp_from = smtp_from

    def send_deployment_notification(
        self,
        to_emails: List[str],
        status: str,
        release_version: str,
        error_message: str = None,
        task_id: str = None,
    ):
        """Send deployment notification email.

        Args:
            to_emails: List of recipient email addresses
            status: Deployment status ('SUCCESS', 'FAILED', 'ROLLBACK_SUCCESS', 'ROLLBACK_FAILED')
            release_version: Release version deployed
            error_message: Error message if failed
            task_id: Task ID
        """
        if not to_emails:
            logger.warning("email.no_recipients", status=status)
            return

        subject = self._get_subject(status, release_version)
        body = self._get_body(status, release_version, error_message, task_id)

        msg = MIMEMultipart("alternative")
        msg["From"] = self.smtp_from
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, to_emails, msg.as_string())

            logger.info(
                "email.sent",
                to=to_emails,
                status=status,
                release=release_version,
            )
        except Exception as e:
            logger.error(
                "email.failed",
                error=str(e),
                to=to_emails,
                status=status,
            )

    def _get_subject(self, status: str, release_version: str) -> str:
        """Get email subject based on status.

        Args:
            status: Deployment status
            release_version: Release version

        Returns:
            Email subject
        """
        subject_map = {
            "SUCCESS": f"✅ Deployment Successful - {release_version}",
            "FAILED": f"❌ Deployment Failed - {release_version}",
            "ROLLBACK_SUCCESS": f"🔄 Rollback Successful - {release_version}",
            "ROLLBACK_FAILED": f"⚠️ Rollback Failed - {release_version}",
        }
        return subject_map.get(status, f"Deployment Notification - {release_version}")

    def _get_body(
        self,
        status: str,
        release_version: str,
        error_message: str = None,
        task_id: str = None,
    ) -> str:
        """Get email body based on status.

        Args:
            status: Deployment status
            release_version: Release version
            error_message: Error message if failed
            task_id: Task ID

        Returns:
            HTML email body
        """
        if status == "SUCCESS":
            return f"""
                <html>
                  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                      <h2 style="color: #28a745; border-bottom: 2px solid #28a745; padding-bottom: 10px;">
                        ✅ Deployment Completed Successfully
                      </h2>
                      <table style="width: 100%; margin-top: 20px;">
                        <tr>
                          <td style="padding: 8px; font-weight: bold; width: 150px;">Release Version:</td>
                          <td style="padding: 8px;">{release_version}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Task ID:</td>
                          <td style="padding: 8px;">{task_id or 'N/A'}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Status:</td>
                          <td style="padding: 8px; color: #28a745;">Deployment completed and services are running.</td>
                        </tr>
                      </table>
                      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                        <p>Generated by WrkTalk Agent</p>
                      </div>
                    </div>
                  </body>
                </html>
            """
        elif status == "FAILED":
            return f"""
                <html>
                  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                      <h2 style="color: #dc3545; border-bottom: 2px solid #dc3545; padding-bottom: 10px;">
                        ❌ Deployment Failed
                      </h2>
                      <table style="width: 100%; margin-top: 20px;">
                        <tr>
                          <td style="padding: 8px; font-weight: bold; width: 150px;">Release Version:</td>
                          <td style="padding: 8px;">{release_version}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Task ID:</td>
                          <td style="padding: 8px;">{task_id or 'N/A'}</td>
                        </tr>
                      </table>
                      <div style="margin-top: 20px;">
                        <p style="font-weight: bold; color: #dc3545;">Error:</p>
                        <pre style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #dc3545; overflow-x: auto; white-space: pre-wrap;">{error_message or 'Unknown error occurred'}</pre>
                      </div>
                      <div style="margin-top: 20px; padding: 15px; background-color: #fff3cd; border-left: 4px solid #ffc107;">
                        <p style="margin: 0;"><strong>Action Required:</strong> Please review the error and take corrective action.</p>
                      </div>
                      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                        <p>Generated by WrkTalk Agent</p>
                      </div>
                    </div>
                  </body>
                </html>
            """
        elif status == "ROLLBACK_SUCCESS":
            return f"""
                <html>
                  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                      <h2 style="color: #17a2b8; border-bottom: 2px solid #17a2b8; padding-bottom: 10px;">
                        🔄 Rollback Completed Successfully
                      </h2>
                      <table style="width: 100%; margin-top: 20px;">
                        <tr>
                          <td style="padding: 8px; font-weight: bold; width: 150px;">Rolled Back To:</td>
                          <td style="padding: 8px;">{release_version}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Task ID:</td>
                          <td style="padding: 8px;">{task_id or 'N/A'}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Status:</td>
                          <td style="padding: 8px; color: #17a2b8;">Rollback completed and services are running on previous version.</td>
                        </tr>
                      </table>
                      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                        <p>Generated by WrkTalk Agent</p>
                      </div>
                    </div>
                  </body>
                </html>
            """
        elif status == "ROLLBACK_FAILED":
            return f"""
                <html>
                  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                      <h2 style="color: #dc3545; border-bottom: 2px solid #dc3545; padding-bottom: 10px;">
                        ⚠️ Rollback Failed
                      </h2>
                      <table style="width: 100%; margin-top: 20px;">
                        <tr>
                          <td style="padding: 8px; font-weight: bold; width: 150px;">Attempted Version:</td>
                          <td style="padding: 8px;">{release_version}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Task ID:</td>
                          <td style="padding: 8px;">{task_id or 'N/A'}</td>
                        </tr>
                      </table>
                      <div style="margin-top: 20px;">
                        <p style="font-weight: bold; color: #dc3545;">Error:</p>
                        <pre style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #dc3545; overflow-x: auto; white-space: pre-wrap;">{error_message or 'Unknown error occurred'}</pre>
                      </div>
                      <div style="margin-top: 20px; padding: 15px; background-color: #f8d7da; border-left: 4px solid #dc3545;">
                        <p style="margin: 0;"><strong>URGENT:</strong> Rollback failed. Manual intervention required immediately.</p>
                      </div>
                      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                        <p>Generated by WrkTalk Agent</p>
                      </div>
                    </div>
                  </body>
                </html>
            """
        else:
            return f"""
                <html>
                  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
                      <h2 style="border-bottom: 2px solid #666; padding-bottom: 10px;">
                        Deployment Notification
                      </h2>
                      <table style="width: 100%; margin-top: 20px;">
                        <tr>
                          <td style="padding: 8px; font-weight: bold; width: 150px;">Release Version:</td>
                          <td style="padding: 8px;">{release_version}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Status:</td>
                          <td style="padding: 8px;">{status}</td>
                        </tr>
                        <tr>
                          <td style="padding: 8px; font-weight: bold;">Task ID:</td>
                          <td style="padding: 8px;">{task_id or 'N/A'}</td>
                        </tr>
                      </table>
                      <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                        <p>Generated by WrkTalk Agent</p>
                      </div>
                    </div>
                  </body>
                </html>
            """
