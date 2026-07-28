from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from src.services.orchestrator import IntegrationOrchestrator
from src.core.security import get_db_connection
import asyncio

class IntegrationScheduler:
    """
    Gerencia tarefas agendadas em segundo plano.
    """
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

    def load_jobs(self):
        """Busca tarefas agendadas na TRB_AGENDAMENTO e as registra."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Limpa jobs antigos antes de recarregar
            self.scheduler.remove_all_jobs()
            
            try:
                # Schema V2
                cursor.execute("""
                    SELECT A.CRON_EXPRESSION, I.NOME_ENDPOINT, A.ID_INTEGRACAO
                    FROM TRB_AGENDAMENTO A
                    JOIN TRB_INTEGRACAO I ON A.ID_INTEGRACAO = I.ID_INTEGRACAO
                    WHERE A.ATIVO = 1 AND I.ATIVO = 1
                """)
            except Exception:
                # Schema V1 (sem agendamento)
                cursor.close()
                conn.close()
                return
            
            for cron, nome, int_id in cursor.fetchall():
                # Define o job de execução
                # Nota: Scheduler executa em thread separada, precisa de loop se for async
                self.scheduler.add_job(
                    self.execute_job,
                    CronTrigger.from_crontab(cron),
                    args=[nome, 0], # Usr_cod 0 para automação
                    id=f"job_{int_id}"
                )
            
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Erro ao carregar agendamentos: {e}")

    def execute_job(self, nome, usr_cod):
        """Worker que executa a integração."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(IntegrationOrchestrator.run(nome, usr_cod, {}))
        finally:
            loop.close()

scheduler_service = IntegrationScheduler()
