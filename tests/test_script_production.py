from alembic.testing.fixtures import TestBase
from alembic.testing import eq_, ne_, assert_raises_message, is_, assertions
from alembic.testing.env import clear_staging_env, staging_env, \
    _get_staging_directory, _no_sql_testing_config, env_file_fixture, \
    script_file_fixture, _testing_config, _sqlite_testing_config, \
    three_rev_fixture, _multi_dir_testing_config, write_script,\
    _sqlite_file_db, _multidb_testing_config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.environment import EnvironmentContext
from alembic.testing import mock
from alembic import util
from alembic.operations import ops
from alembic import autogenerate
import os
import datetime
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector
from alembic.util import CommandError
import re

env, abc, def_ = None, None, None


class GeneralOrderedTests(TestBase):

    def setUp(self):
        global env
        env = staging_env()

    def tearDown(self):
        clear_staging_env()

    def test_steps(self):
        self._test_001_environment()
        self._test_002_rev_ids()
        self._test_003_api_methods_clean()
        self._test_004_rev()
        self._test_005_nextrev()
        self._test_006_from_clean_env()
        self._test_007_long_name()
        self._test_008_long_name_configurable()

    def _test_001_environment(self):
        assert_set = set(['env.py', 'script.py.mako', 'README'])
        eq_(
            assert_set.intersection(os.listdir(env.dir)),
            assert_set
        )

    def _test_002_rev_ids(self):
        global abc, def_
        abc = util.rev_id()
        def_ = util.rev_id()
        ne_(abc, def_)

    def _test_003_api_methods_clean(self):
        eq_(env.get_heads(), [])

        eq_(env.get_base(), None)

    def _test_004_rev(self):
        script = env.generate_revision(abc, "this is a message", refresh=True)
        eq_(script.doc, "this is a message")
        eq_(script.revision, abc)
        eq_(script.down_revision, None)
        assert os.access(
            os.path.join(env.dir, 'versions',
                         '%s_this_is_a_message.py' % abc), os.F_OK)
        assert callable(script.module.upgrade)
        eq_(env.get_heads(), [abc])
        eq_(env.get_base(), abc)

    def _test_005_nextrev(self):
        script = env.generate_revision(
            def_, "this is the next rev", refresh=True)
        assert os.access(
            os.path.join(
                env.dir, 'versions',
                '%s_this_is_the_next_rev.py' % def_), os.F_OK)
        eq_(script.revision, def_)
        eq_(script.down_revision, abc)
        eq_(env.get_revision(abc).nextrev, set([def_]))
        assert script.module.down_revision == abc
        assert callable(script.module.upgrade)
        assert callable(script.module.downgrade)
        eq_(env.get_heads(), [def_])
        eq_(env.get_base(), abc)

    def _test_006_from_clean_env(self):
        # test the environment so far with a
        # new ScriptDirectory instance.

        env = staging_env(create=False)
        abc_rev = env.get_revision(abc)
        def_rev = env.get_revision(def_)
        eq_(abc_rev.nextrev, set([def_]))
        eq_(abc_rev.revision, abc)
        eq_(def_rev.down_revision, abc)
        eq_(env.get_heads(), [def_])
        eq_(env.get_base(), abc)

    def _test_007_long_name(self):
        rid = util.rev_id()
        env.generate_revision(rid,
                              "this is a really long name with "
                              "lots of characters and also "
                              "I'd like it to\nhave\nnewlines")
        assert os.access(
            os.path.join(
                env.dir, 'versions',
                '%s_this_is_a_really_long_name_with_lots_of_.py' % rid),
            os.F_OK)

    def _test_008_long_name_configurable(self):
        env.truncate_slug_length = 60
        rid = util.rev_id()
        env.generate_revision(rid,
                              "this is a really long name with "
                              "lots of characters and also "
                              "I'd like it to\nhave\nnewlines")
        assert os.access(
            os.path.join(env.dir, 'versions',
                         '%s_this_is_a_really_long_name_with_lots_'
                         'of_characters_and_also_.py' % rid),
            os.F_OK)


class ScriptNamingTest(TestBase):

    @classmethod
    def setup_class(cls):
        _testing_config()

    @classmethod
    def teardown_class(cls):
        clear_staging_env()

    def test_args(self):
        script = ScriptDirectory(
            _get_staging_directory(),
            file_template="%(rev)s_%(slug)s_"
            "%(year)s_%(month)s_"
            "%(day)s_%(hour)s_"
            "%(minute)s_%(second)s"
        )
        create_date = datetime.datetime(2012, 7, 25, 15, 8, 5)
        eq_(
            script._rev_path(
                script.versions, "12345", "this is a message", create_date),
            os.path.abspath(
                "%s/versions/12345_this_is_a_"
                "message_2012_7_25_15_8_5.py" % _get_staging_directory())
        )


class RevisionCommandTest(TestBase):
    def setUp(self):
        self.env = staging_env()
        self.cfg = _sqlite_testing_config()
        self.a, self.b, self.c = three_rev_fixture(self.cfg)

    def tearDown(self):
        clear_staging_env()

    def test_create_script_basic(self):
        rev = command.revision(self.cfg, message="some message")
        script = ScriptDirectory.from_config(self.cfg)
        rev = script.get_revision(rev.revision)
        eq_(rev.down_revision, self.c)
        assert "some message" in rev.doc

    def test_create_script_splice(self):
        rev = command.revision(
            self.cfg, message="some message", head=self.b, splice=True)
        script = ScriptDirectory.from_config(self.cfg)
        rev = script.get_revision(rev.revision)
        eq_(rev.down_revision, self.b)
        assert "some message" in rev.doc
        eq_(set(script.get_heads()), set([rev.revision, self.c]))

    def test_create_script_missing_splice(self):
        assert_raises_message(
            util.CommandError,
            "Revision %s is not a head revision; please specify --splice "
            "to create a new branch from this revision" % self.b,
            command.revision,
            self.cfg, message="some message", head=self.b
        )

    def test_create_script_branches(self):
        rev = command.revision(
            self.cfg, message="some message", branch_label="foobar")
        script = ScriptDirectory.from_config(self.cfg)
        rev = script.get_revision(rev.revision)
        eq_(script.get_revision("foobar"), rev)

    def test_create_script_branches_old_template(self):
        script = ScriptDirectory.from_config(self.cfg)
        with open(os.path.join(script.dir, "script.py.mako"), "w") as file_:
            file_.write(
                "<%text>#</%text> ${message}\n"
                "revision = ${repr(up_revision)}\n"
                "down_revision = ${repr(down_revision)}\n\n"
                "def upgrade():\n"
                "    ${upgrades if upgrades else 'pass'}\n\n"
                "def downgrade():\n"
                "    ${downgrade if downgrades else 'pass'}\n\n"
            )

        # works OK if no branch names
        command.revision(self.cfg, message="some message")

        assert_raises_message(
            util.CommandError,
            r"Version \w+ specified branch_labels foobar, "
            r"however the migration file .+?\b does not have them; have you "
            "upgraded your script.py.mako to include the 'branch_labels' "
            r"section\?",
            command.revision,
            self.cfg, message="some message", branch_label="foobar"
        )




class CustomizeRevisionTest(TestBase):
    def setUp(self):
        self.env = staging_env()
        self.cfg = _multi_dir_testing_config()
        self.cfg.set_main_option("revision_environment", "true")

        script = ScriptDirectory.from_config(self.cfg)
        self.model1 = util.rev_id()
        self.model2 = util.rev_id()
        self.model3 = util.rev_id()
        for model, name in [
            (self.model1, "model1"),
            (self.model2, "model2"),
            (self.model3, "model3"),
        ]:
            script.generate_revision(
                model, name, refresh=True,
                version_path=os.path.join(_get_staging_directory(), name),
                head="base")

            write_script(script, model, """\
"%s"
revision = '%s'
down_revision = None
branch_labels = ['%s']

from alembic import op


def upgrade():
    pass


def downgrade():
    pass

""" % (name, model, name))

    def tearDown(self):
        clear_staging_env()

    def _env_fixture(self, fn, target_metadata):
        self.engine = engine = _sqlite_file_db()

        def run_env(self):
            from alembic import context

            with engine.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    process_revision_directives=fn)
                with context.begin_transaction():
                    context.run_migrations()

        return mock.patch(
            "alembic.script.base.ScriptDirectory.run_env",
            run_env
        )

    def test_new_locations_no_autogen(self):
        m = sa.MetaData()

        def process_revision_directives(context, rev, generate_revisions):
            generate_revisions[:] = [
                ops.MigrationScript(
                    util.rev_id(),
                    ops.UpgradeOps(),
                    ops.DowngradeOps(),
                    version_path=os.path.join(
                        _get_staging_directory(), "model1"),
                    head="model1@head"
                ),
                ops.MigrationScript(
                    util.rev_id(),
                    ops.UpgradeOps(),
                    ops.DowngradeOps(),
                    version_path=os.path.join(
                        _get_staging_directory(), "model2"),
                    head="model2@head"
                ),
                ops.MigrationScript(
                    util.rev_id(),
                    ops.UpgradeOps(),
                    ops.DowngradeOps(),
                    version_path=os.path.join(
                        _get_staging_directory(), "model3"),
                    head="model3@head"
                ),
            ]

        with self._env_fixture(process_revision_directives, m):
            revs = command.revision(self.cfg, message="some message")

        script = ScriptDirectory.from_config(self.cfg)

        for rev, model in [
            (revs[0], "model1"),
            (revs[1], "model2"),
            (revs[2], "model3"),
        ]:
            rev_script = script.get_revision(rev.revision)
            eq_(
                rev_script.path,
                os.path.abspath(os.path.join(
                    _get_staging_directory(), model,
                    "%s_.py" % (rev_script.revision, )
                ))
            )
            assert os.path.exists(rev_script.path)

    def test_renders_added_directives_no_autogen(self):
        m = sa.MetaData()

        def process_revision_directives(context, rev, generate_revisions):
            generate_revisions[0].upgrade_ops.ops.append(
                ops.CreateIndexOp("some_index", "some_table", ["a", "b"])
            )

        with self._env_fixture(process_revision_directives, m):
            rev = command.revision(
                self.cfg, message="some message", head="model1@head", sql=True)

        with mock.patch.object(rev.module, "op") as op_mock:
            rev.module.upgrade()
        eq_(
            op_mock.mock_calls,
            [mock.call.create_index(
                'some_index', 'some_table', ['a', 'b'], unique=False)]
        )

    def test_autogen(self):
        m = sa.MetaData()
        sa.Table('t', m, sa.Column('x', sa.Integer))

        def process_revision_directives(context, rev, generate_revisions):
            existing_upgrades = generate_revisions[0].upgrade_ops
            existing_downgrades = generate_revisions[0].downgrade_ops

            # model1 will run the upgrades, e.g. create the table,
            # model2 will run the downgrades as upgrades, e.g. drop
            # the table again

            generate_revisions[:] = [
                ops.MigrationScript(
                    util.rev_id(),
                    existing_upgrades,
                    ops.DowngradeOps(),
                    version_path=os.path.join(
                        _get_staging_directory(), "model1"),
                    head="model1@head"
                ),
                ops.MigrationScript(
                    util.rev_id(),
                    ops.UpgradeOps(ops=existing_downgrades.ops),
                    ops.DowngradeOps(),
                    version_path=os.path.join(
                        _get_staging_directory(), "model2"),
                    head="model2@head"
                )
            ]

        with self._env_fixture(process_revision_directives, m):
            command.upgrade(self.cfg, "heads")

            eq_(
                Inspector.from_engine(self.engine).get_table_names(),
                ["alembic_version"]
            )

            command.revision(
                self.cfg, message="some message",
                autogenerate=True)

            command.upgrade(self.cfg, "model1@head")

            eq_(
                Inspector.from_engine(self.engine).get_table_names(),
                ["alembic_version", "t"]
            )

            command.upgrade(self.cfg, "model2@head")

            eq_(
                Inspector.from_engine(self.engine).get_table_names(),
                ["alembic_version"]
            )


class ScriptAccessorTest(TestBase):
    def test_upgrade_downgrade_ops_list_accessors(self):
        u1 = ops.UpgradeOps(ops=[])
        d1 = ops.DowngradeOps(ops=[])
        m1 = ops.MigrationScript(
            "somerev", u1, d1
        )
        is_(
            m1.upgrade_ops, u1
        )
        is_(
            m1.downgrade_ops, d1
        )
        u2 = ops.UpgradeOps(ops=[])
        d2 = ops.DowngradeOps(ops=[])
        m1._upgrade_ops.append(u2)
        m1._downgrade_ops.append(d2)

        assert_raises_message(
            ValueError,
            "This MigrationScript instance has a multiple-entry list for "
            "UpgradeOps; please use the upgrade_ops_list attribute.",
            getattr, m1, "upgrade_ops"
        )
        assert_raises_message(
            ValueError,
            "This MigrationScript instance has a multiple-entry list for "
            "DowngradeOps; please use the downgrade_ops_list attribute.",
            getattr, m1, "downgrade_ops"
        )
        eq_(m1.upgrade_ops_list, [u1, u2])
        eq_(m1.downgrade_ops_list, [d1, d2])


class ImportsTest(TestBase):
    def setUp(self):
        self.env = staging_env()
        self.cfg = _sqlite_testing_config()

    def tearDown(self):
        clear_staging_env()

    def _env_fixture(self, target_metadata):
        self.engine = engine = _sqlite_file_db()

        def run_env(self):
            from alembic import context

            with engine.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata)
                with context.begin_transaction():
                    context.run_migrations()

        return mock.patch(
            "alembic.script.base.ScriptDirectory.run_env",
            run_env
        )

    def test_imports_in_script(self):
        from sqlalchemy import MetaData, Table, Column
        from sqlalchemy.dialects.mysql import VARCHAR

        type_ = VARCHAR(20, charset='utf8', national=True)

        m = MetaData()

        Table(
            't', m,
            Column('x', type_)
        )

        with self._env_fixture(m):
            rev = command.revision(
                self.cfg, message="some message",
                autogenerate=True)

        with open(rev.path) as file_:
            assert "from sqlalchemy.dialects import mysql" in file_.read()


class MultiContextTest(TestBase):
    """test the multidb template for autogenerate front-to-back"""

    def setUp(self):
        self.engine1 = _sqlite_file_db(tempname='eng1.db')
        self.engine2 = _sqlite_file_db(tempname='eng2.db')
        self.engine3 = _sqlite_file_db(tempname='eng3.db')

        self.env = staging_env(template="multidb")
        self.cfg = _multidb_testing_config({
            "engine1": self.engine1,
            "engine2": self.engine2,
            "engine3": self.engine3
        })

    def _write_metadata(self, meta):
        path = os.path.join(_get_staging_directory(), 'scripts', 'env.py')
        with open(path) as env_:
            existing_env = env_.read()
        existing_env = existing_env.replace(
            "target_metadata = {}",
            meta)
        with open(path, "w") as env_:
            env_.write(existing_env)

    def tearDown(self):
        clear_staging_env()

    def test_autogen(self):
        self._write_metadata(
            """
import sqlalchemy as sa

m1 = sa.MetaData()
m2 = sa.MetaData()
m3 = sa.MetaData()
target_metadata = {"engine1": m1, "engine2": m2, "engine3": m3}

sa.Table('e1t1', m1, sa.Column('x', sa.Integer))
sa.Table('e2t1', m2, sa.Column('y', sa.Integer))
sa.Table('e3t1', m3, sa.Column('z', sa.Integer))

"""
        )

        rev = command.revision(
            self.cfg, message="some message",
            autogenerate=True
        )
        with mock.patch.object(rev.module, "op") as op_mock:
            rev.module.upgrade_engine1()
            eq_(
                op_mock.mock_calls[-1],
                mock.call.create_table('e1t1', mock.ANY)
            )
            rev.module.upgrade_engine2()
            eq_(
                op_mock.mock_calls[-1],
                mock.call.create_table('e2t1', mock.ANY)
            )
            rev.module.upgrade_engine3()
            eq_(
                op_mock.mock_calls[-1],
                mock.call.create_table('e3t1', mock.ANY)
            )
            rev.module.downgrade_engine1()
            eq_(
                op_mock.mock_calls[-1],
                mock.call.drop_table('e1t1')
            )
            rev.module.downgrade_engine2()
            eq_(
                op_mock.mock_calls[-1],
                mock.call.drop_table('e2t1')
            )
            rev.module.downgrade_engine3()
            eq_(
                op_mock.mock_calls[-1],
                mock.call.drop_table('e3t1')
            )


class RewriterTest(TestBase):
    def test_all_traverse(self):
        writer = autogenerate.Rewriter()

        mocker = mock.Mock(side_effect=lambda context, revision, op: op)
        writer.rewrites(ops.MigrateOperation)(mocker)

        addcolop = ops.AddColumnOp(
            't1', sa.Column('x', sa.Integer())
        )

        directives = [
            ops.MigrationScript(
                util.rev_id(),
                ops.UpgradeOps(ops=[
                    ops.ModifyTableOps('t1', ops=[
                        addcolop
                    ])
                ]),
                ops.DowngradeOps(ops=[
                ]),
            )
        ]

        ctx, rev = mock.Mock(), mock.Mock()
        writer(ctx, rev, directives)
        eq_(
            mocker.mock_calls,
            [
                mock.call(ctx, rev, directives[0]),
                mock.call(ctx, rev, directives[0].upgrade_ops),
                mock.call(ctx, rev, directives[0].upgrade_ops.ops[0]),
                mock.call(ctx, rev, addcolop),
                mock.call(ctx, rev, directives[0].downgrade_ops),
            ]
        )

    def test_double_migrate_table(self):
        writer = autogenerate.Rewriter()

        idx_ops = []

        @writer.rewrites(ops.ModifyTableOps)
        def second_table(context, revision, op):
            return [
                op,
                ops.ModifyTableOps('t2', ops=[
                    ops.AddColumnOp('t2', sa.Column('x', sa.Integer()))
                ])
            ]

        @writer.rewrites(ops.AddColumnOp)
        def add_column(context, revision, op):
            idx_op = ops.CreateIndexOp('ixt', op.table_name, [op.column.name])
            idx_ops.append(idx_op)
            return [
                op,
                idx_op
            ]

        directives = [
            ops.MigrationScript(
                util.rev_id(),
                ops.UpgradeOps(ops=[
                    ops.ModifyTableOps('t1', ops=[
                        ops.AddColumnOp('t1', sa.Column('x', sa.Integer()))
                    ])
                ]),
                ops.DowngradeOps(ops=[]),
            )
        ]

        ctx, rev = mock.Mock(), mock.Mock()
        writer(ctx, rev, directives)
        eq_(
            [d.table_name for d in directives[0].upgrade_ops.ops],
            ['t1', 't2']
        )
        is_(
            directives[0].upgrade_ops.ops[0].ops[1],
            idx_ops[0]
        )
        is_(
            directives[0].upgrade_ops.ops[1].ops[1],
            idx_ops[1]
        )

    def test_chained_ops(self):
        writer1 = autogenerate.Rewriter()
        writer2 = autogenerate.Rewriter()

        @writer1.rewrites(ops.AddColumnOp)
        def add_column_nullable(context, revision, op):
            if op.column.nullable:
                return op
            else:
                op.column.nullable = True
                return [
                    op,
                    ops.AlterColumnOp(
                        op.table_name,
                        op.column.name,
                        modify_nullable=False,
                        existing_type=op.column.type,
                    )
                ]

        @writer2.rewrites(ops.AddColumnOp)
        def add_column_idx(context, revision, op):
            idx_op = ops.CreateIndexOp('ixt', op.table_name, [op.column.name])
            return [
                op,
                idx_op
            ]

        directives = [
            ops.MigrationScript(
                util.rev_id(),
                ops.UpgradeOps(ops=[
                    ops.ModifyTableOps('t1', ops=[
                        ops.AddColumnOp(
                            't1', sa.Column('x', sa.Integer(), nullable=False))
                    ])
                ]),
                ops.DowngradeOps(ops=[]),
            )
        ]

        ctx, rev = mock.Mock(), mock.Mock()
        writer1.chain(writer2)(ctx, rev, directives)

        eq_(
            autogenerate.render_python_code(directives[0].upgrade_ops),
            "# ### commands auto generated by Alembic - please adjust! ###\n"
            "    op.add_column('t1', "
            "sa.Column('x', sa.Integer(), nullable=True))\n"
            "    op.create_index('ixt', 't1', ['x'], unique=False)\n"
            "    op.alter_column('t1', 'x',\n"
            "               existing_type=sa.Integer(),\n"
            "               nullable=False)\n"
            "    # ### end Alembic commands ###"
        )


class MultiDirRevisionCommandTest(TestBase):
    def setUp(self):
        self.env = staging_env()
        self.cfg = _multi_dir_testing_config()

    def tearDown(self):
        clear_staging_env()

    def test_multiple_dir_no_bases(self):
        assert_raises_message(
            util.CommandError,
            "Multiple version locations present, please specify "
            "--version-path",
            command.revision, self.cfg, message="some message"
        )

    def test_multiple_dir_no_bases_invalid_version_path(self):
        assert_raises_message(
            util.CommandError,
            "Path foo/bar/ is not represented in current version locations",
            command.revision,
            self.cfg, message="x",
            version_path=os.path.join("foo/bar/")
        )

    def test_multiple_dir_no_bases_version_path(self):
        script = command.revision(
            self.cfg, message="x",
            version_path=os.path.join(_get_staging_directory(), "model1"))
        assert os.access(script.path, os.F_OK)

    def test_multiple_dir_chooses_base(self):
        command.revision(
            self.cfg, message="x",
            head="base",
            version_path=os.path.join(_get_staging_directory(), "model1"))

        script2 = command.revision(
            self.cfg, message="y",
            head="base",
            version_path=os.path.join(_get_staging_directory(), "model2"))

        script3 = command.revision(
            self.cfg, message="y2",
            head=script2.revision)

        eq_(
            os.path.dirname(script3.path),
            os.path.abspath(os.path.join(_get_staging_directory(), "model2"))
        )
        assert os.access(script3.path, os.F_OK)


class TemplateArgsTest(TestBase):

    def setUp(self):
        staging_env()
        self.cfg = _no_sql_testing_config(
            directives="\nrevision_environment=true\n"
        )

    def tearDown(self):
        clear_staging_env()

    def test_args_propagate(self):
        config = _no_sql_testing_config()
        script = ScriptDirectory.from_config(config)
        template_args = {"x": "x1", "y": "y1", "z": "z1"}
        env = EnvironmentContext(
            config,
            script,
            template_args=template_args
        )
        env.configure(dialect_name="sqlite",
                      template_args={"y": "y2", "q": "q1"})
        eq_(
            template_args,
            {"x": "x1", "y": "y2", "z": "z1", "q": "q1"}
        )

    def test_tmpl_args_revision(self):
        env_file_fixture("""
context.configure(dialect_name='sqlite', template_args={"somearg":"somevalue"})
""")
        script_file_fixture("""
# somearg: ${somearg}
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
""")

        command.revision(self.cfg, message="some rev")
        script = ScriptDirectory.from_config(self.cfg)

        rev = script.get_revision('head')
        with open(rev.path) as f:
            text = f.read()
        assert "somearg: somevalue" in text

    def test_bad_render(self):
        env_file_fixture("""
context.configure(dialect_name='sqlite', template_args={"somearg":"somevalue"})
""")
        script_file_fixture("""
    <% z = x + y %>
""")

        try:
            command.revision(self.cfg, message="some rev")
        except CommandError as ce:
            m = re.match(
                r"^Template rendering failed; see (.+?) "
                "for a template-oriented",
                str(ce)
            )
            assert m, "Command error did not produce a file"
            contents = open(m.group(1)).read()
            os.remove(m.group(1))
            assert "<% z = x + y %>" in contents


class DuplicateVersionLocationsTest(TestBase):

    def setUp(self):
        self.env = staging_env()
        self.cfg = _multi_dir_testing_config(
            # this is a duplicate of one of the paths
            # already present in this fixture
            extra_version_location='%(here)s/model1'
        )

        script = ScriptDirectory.from_config(self.cfg)
        self.model1 = util.rev_id()
        self.model2 = util.rev_id()
        self.model3 = util.rev_id()
        for model, name in [
            (self.model1, "model1"),
            (self.model2, "model2"),
            (self.model3, "model3"),
        ]:
            script.generate_revision(
                model, name, refresh=True,
                version_path=os.path.join(_get_staging_directory(), name),
                head="base")
            write_script(script, model, """\
"%s"
revision = '%s'
down_revision = None
branch_labels = ['%s']

from alembic import op


def upgrade():
    pass


def downgrade():
    pass

""" % (name, model, name))

    def tearDown(self):
        clear_staging_env()

    def test_env_emits_warning(self):
        with assertions.expect_warnings(
            "File %s loaded twice! ignoring. "
            "Please ensure version_locations is unique" % (
                os.path.realpath(os.path.join(
                _get_staging_directory(),
                "model1",
                "%s_model1.py" % self.model1
                )))
        ):
            script = ScriptDirectory.from_config(self.cfg)
            script.revision_map.heads
            eq_(
                [rev.revision for rev in script.walk_revisions()],
                [self.model1, self.model2, self.model3]
            )