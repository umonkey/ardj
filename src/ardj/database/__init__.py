# vim: set ts=4 sts=4 sw=4 et fileencoding=utf-8:
#
# database related functions for ardj.
#
# ardj is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# ardj is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import

import ardj
import ardj.settings


instance = None


def Open():
    """Returns the active database instance."""
    global instance, ardj
    if instance is None:
        dsn = ardj.settings.get('database', {})
        dsn_type = dsn.get("type")
        if dsn_type == "sqlite":
            import ardj.database.sqlite
            connector = ardj.database.sqlite.Open
        elif dsn_type == "mysql":
            import ardj.database.mysql
            connector = ardj.database.mysql.Open
        del dsn["type"]
        instance = connector(**dsn)
    return instance
