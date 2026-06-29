#!/usr/bin/env python3
"""tcm-db 最小 ETL 入口（v0.2）。

诚实限制：
- 不引入框架（纯标准库 + sqlite3）
- 不实现 formulas 历史导入器（缺失，P1 工程债；数据库为权威产物不可从源重建）
- 不调用 populate.py build()（空壳）
- 不宣称支持 --rebuild
- case-ingest 步骤 BLOCKED：clinical_cases 无可靠稳定来源身份键
  （见 docs/clinical-cases-idempotency-analysis.md），未实施幂等导入，避免假幂等

支持：
  --check              报告 clinical_cases 来源键状态（只读，不写入）
  --step check         同上
  --step case-ingest   BLOCKED（非0退出，提示方案 A/B/C）
  --step formulas-ingest  NOT IMPLEMENTED（非0退出）
  --dry-run            不写入（check 本就只读）
  --db / --source-root
  -v                   详细日志
"""
import argparse, logging, sqlite3, sys
from pathlib import Path

log = logging.getLogger('etl')


def setup_logging(verbose):
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')


def get_conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')  # 写入路径必须开外键
    return conn


def check_sources(conn):
    """报告 clinical_cases 来源键状态。返回 (stats, issues)。issues 非空 → 幂等不可靠。"""
    stats = {}
    stats['total'] = conn.execute('SELECT COUNT(*) FROM clinical_cases').fetchone()[0]
    for col in ['source_repo', 'raw_path', 'patient_id', 'case_date']:
        stats[col + '_null'] = conn.execute(
            f'SELECT COUNT(*) FROM clinical_cases WHERE {col} IS NULL OR {col}=""').fetchone()[0]
    stats['raw_path_dup_groups'] = conn.execute(
        'SELECT COUNT(*) FROM (SELECT raw_path,COUNT(*) n FROM clinical_cases '
        'WHERE raw_path!="" GROUP BY raw_path HAVING n>1)').fetchone()[0]
    stats['patient_id_dup_groups'] = conn.execute(
        'SELECT COUNT(*) FROM (SELECT patient_id,COUNT(*) n FROM clinical_cases '
        'GROUP BY patient_id HAVING n>1)').fetchone()[0]
    stats['combo_dup_groups'] = conn.execute(
        'SELECT COUNT(*) FROM (SELECT source_repo,raw_path,patient_id,COUNT(*) n '
        'FROM clinical_cases WHERE raw_path!="" GROUP BY source_repo,raw_path,patient_id HAVING n>1)').fetchone()[0]
    stats['multi_case_files'] = conn.execute(
        'SELECT COUNT(*) FROM (SELECT raw_path,COUNT(*) n,COUNT(DISTINCT chief_complaint) dc '
        'FROM clinical_cases WHERE raw_path!="" GROUP BY raw_path HAVING n>1 AND dc>1)').fetchone()[0]
    has_uniq = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE tbl_name='clinical_cases' AND sql LIKE '%UNIQUE%'").fetchone()[0]
    stats['has_unique_constraint'] = has_uniq > 0

    issues = []
    if stats['raw_path_null'] > 0:
        issues.append(f"raw_path 有 {stats['raw_path_null']} 行空（非稳定来源键）")
    if stats['multi_case_files'] > 0:
        issues.append(f"{stats['multi_case_files']} 个文件含多案（raw_path 非身份键）")
    if stats['patient_id_dup_groups'] > 0:
        issues.append(f"patient_id {stats['patient_id_dup_groups']} 重复组（实为标题非身份）")
    if not stats['has_unique_constraint']:
        issues.append("无 UNIQUE 约束（裸 INSERT 无法幂等）")
    return stats, issues


def cmd_check(args):
    if not Path(args.db).exists():
        log.error(f'数据库不存在: {args.db}')
        return 3
    conn = get_conn(args.db)
    try:
        stats, issues = check_sources(conn)
        log.info('clinical_cases 来源键检查（只读）:')
        for k, v in stats.items():
            log.info(f'  {k}: {v}')
        if issues:
            log.warning('来源键问题（阻碍幂等导入）:')
            for i in issues:
                log.warning(f'  - {i}')
            log.warning('case-ingest BLOCKED：无可靠稳定来源身份键。'
                        '见 docs/clinical-cases-idempotency-analysis.md（方案 A/B/C 待决策）')
            return 1
        log.info('来源键 OK，可考虑实施幂等导入')
        return 0
    finally:
        conn.close()


def cmd_step_list():
    log.info('可用步骤:')
    log.info('  check            报告来源键状态（只读，可执行）')
    log.info('  case-ingest      BLOCKED（无可靠来源键，待决策方案 A/B/C）')
    log.info('  formulas-ingest  NOT IMPLEMENTED（历史导入器缺失，P1）')
    return 0


def main():
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description='tcm-db 最小 ETL 入口')
    ap.add_argument('--db', default=str(here / 'tcm_knowledge.db'))
    ap.add_argument('--source-root', default=str(here.parent))
    ap.add_argument('--step', choices=['check', 'case-ingest', 'formulas-ingest'])
    ap.add_argument('--check', action='store_true', help='同 --step check')
    ap.add_argument('--dry-run', action='store_true', help='不写入（check 本就只读）')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()
    setup_logging(args.verbose)

    if args.check or args.step == 'check':
        return cmd_check(args)
    if args.step == 'case-ingest':
        log.error('case-ingest BLOCKED：clinical_cases 无可靠稳定来源身份键'
                  '（见 docs/clinical-cases-idempotency-analysis.md）。未实施幂等导入，避免假幂等。')
        return 2
    if args.step == 'formulas-ingest':
        log.error('formulas-ingest NOT IMPLEMENTED：历史 formulas 导入器缺失（P1 工程债）。'
                  '数据库为权威产物，不可从源重建。')
        return 2
    return cmd_step_list()


if __name__ == '__main__':
    sys.exit(main())
