# ytcc - The YouTube channel checker
# Copyright (C) 2019  Wolfgang Popp
#
# This file is part of ytcc.
#
# ytcc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ytcc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ytcc.  If not, see <http://www.gnu.org/licenses/>.

from typing import TypeVar, Optional, Callable, Iterable

# pylint: disable=invalid-name
T = TypeVar("T")


def unpack_optional(elem: Optional[T], default: Callable[[], T]) -> T:
    if elem is None:
        return default()
    return elem


def unpack_or_raise(elem: Optional[T], exception: Exception) -> T:
    if elem is None:
        raise exception
    return elem


def take(amount: int, iterable: Iterable[T]) -> Iterable[T]:
    for _, elem in zip(range(amount), iterable):
        yield elem
