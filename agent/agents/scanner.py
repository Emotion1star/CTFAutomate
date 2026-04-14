import json
import traceback
import uuid
from agents.actioner import execute_solution
from agents.solutioner import get_solutions
from utils.logger import logger
from utils import sql_helper, task_helper, flagUtil
from config import config

import concurrent.futures

def vuln_scan(page, key, simple_key, explorer_pages, task_id):
    from utils.agent_manager import agent_manager

    # 发送 pure 消息，开始获取漏洞检测思路（running状态）
    solution_message = agent_manager.send_pure_message_with_status(
        agent_manager.current_task_id,
        content=f"🎯 开始获取 {page['name']} 页面的漏洞检测思路",
        status="running"
    )
    session_id = solution_message.get('id')
    
    try:
        solutions = get_solutions(page, simple_key, session_id=session_id)
        if config.FOCUS_VULNS:
            solutions = [solution for solution in solutions if solution["vuln"] in config.FOCUS_VULNS]
            agent_manager.send_pure_message(
                agent_manager.current_task_id,
                f"🎯 当前按题目描述聚焦测试：{','.join(config.FOCUS_VULNS)}"
            )
        
        # 更新消息状态为获取漏洞检测思路完成
        if solution_message:
            agent_manager.update_pure_message_status(
                solution_message.get('id'),
                "finish",
                f"✅ 获取 {page['name']} 页面漏洞检测思路完成，共 {len(solutions)} 种思路"
            )
        
        # 调用 agent_manager 发送漏洞检测思路消息
        agent_manager.send_solution_message(agent_manager.current_task_id, solutions, content=f"📋 {page['name']} 页面漏洞检测思路")
        

        
        all_results = []
        vulns = task_helper.get_all_vulns(task_id)

        # 创建线程池执行器
        with concurrent.futures.ThreadPoolExecutor(max_workers=config.MAX_SOLUTION_WORKERS) as executor:
            # 创建任务列表
            future_to_solution = {
                executor.submit(execute_solution, s, page, key, {str(uuid.uuid4()):explorer_pages[i] for i in range(len(explorer_pages))}, vulns): s
                for s in solutions
            }

            # 获取执行结果
            for future in concurrent.futures.as_completed(future_to_solution, timeout=3600):
                s = future_to_solution[future]
                try:
                    result = future.result(timeout=1200)
                    # vuln_result = f"是否存在漏洞：{result['vuln']} 是否需要深入利用：{result['needDeep']} 说明：{result['key']}"
                    logger.info(f"检测思路 【{s}】结果：{result}")
                    if result and 'result' in result and result['result']:
                        all_results.append(result['summary'])

                        if result['summary']['vuln'] == 'True':
                            sql_helper.SQLiteHelper.insert_record(
                                table='vulns',
                                data={
                                    'id': str(uuid.uuid4()),
                                    'task_id': task_id,
                                    'vuln_type': result['summary']['vuln_type'],
                                    'desc': result['summary']['desc'],
                                    'request_json': json.dumps(result['request']),
                                }
                            )

                except concurrent.futures.TimeoutError:
                    logger.error(f"检测思路 【{s}】执行超时 (1200秒)")
                    continue
                except Exception as e:
                    traceback.print_exc()
                    logger.error(f"执行漏洞检测思路异常: {str(e)}")
                    # 如果有异常，更新执行消息为错误状态
                    continue


            
    except concurrent.futures.TimeoutError:
        logger.error(f"漏洞扫描整体执行超时 (3600秒)")
        if solution_message:
            agent_manager.update_pure_message_status(
                solution_message.get('id'),
                "error",
                f"❌ {page['name']} 页面漏洞检测超时 (3600秒)"
            )
    except Exception as e:
        traceback.print_exc()
        logger.error(f"获取漏洞检测思路异常: {str(e)}")
        # 如果获取漏洞检测思路失败，更新消息为错误状态
        if solution_message:
            agent_manager.update_pure_message_status(
                solution_message.get('id'),
                "error",
                f"❌ 获取 {page['name']} 页面漏洞检测思路失败: {str(e)}"
            )
        raise e
        
    return all_results
