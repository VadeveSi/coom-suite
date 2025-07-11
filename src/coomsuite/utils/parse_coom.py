"""
The COOM parser.

Traverses the abstract syntax tree of the COOM input
in a visitor style fashion and outputs ASP facts.
"""

# flake8: noqa
# pylint: skip-file
# mypy: ignore-errors
import sys
from __future__ import annotations  # Required for recursive dataclasses
from typing import List, Optional

try:
    from .coom_grammar.model.ModelParser import ModelParser
    from .coom_grammar.model.ModelVisitor import ModelVisitor
    from .coom_grammar.user.UserInputParser import UserInputParser
    from .coom_grammar.user.UserInputVisitor import UserInputVisitor
except ModuleNotFoundError:  # nocoverage
    print("COOM grammar files not found. Please run \n\n     ./build_grammar.sh")
    sys.exit(1)


class ASPUserInputVisitor(UserInputVisitor):
    """
    Custom visitor of the COOM Parser.
    Custom visitor of the COOM User Input Parser.
    Generates a list of ASP facts as strings.
    """

    def __init__(self) -> None:
        super().__init__()
        self.context: str = ""
        self.output_asp: List[str] = []

    def visitInput_block(self, ctx: UserInputParser.Input_blockContext):
        self.context = ctx.path().getText() + "."
        super().visitInput_block(ctx)
        self.context = ""

    def visitSet_value(self, ctx: UserInputParser.Set_valueContext):
        path = self.context + ctx.path().getText()
        value = ctx.formula_atom().getText()
        is_str = ctx.formula_atom().path() is not None
        if is_str:
            self.output_asp.append(f'user_value("root.{path}","{value}").')
        else:
            self.output_asp.append(f'user_value("root.{path}",{value}).')
        super().visitSet_value(ctx)

    def visitAdd_instance(self, ctx: UserInputParser.Add_instanceContext):
        path = self.context + ctx.path().getText()
        self.output_asp.append(f'user_include("root.{path}").')
        super().visitAdd_instance(ctx)


class ASPModelVisitor(ModelVisitor):
    """
    Custom visitor of the COOM Parser.
    Generates a list of ASP facts as strings.
    """

    def __init__(self) -> None:
        super().__init__()
        self.parent_enum: Optional[ModelParser.EnumerationContext] = None
        self.root_name: str = "product"
        self.structure_name: str = self.root_name
        self.context: str = self.root_name
        self.constraint_idx: int = 0
        self.condition_idx: int = 0
        self.row_idx: int = 0
        self.print_path: bool = True
        self.output_asp: List[str] = []


    def visitProduct(self, ctx: ModelParser.ProductContext):
        self.output_asp.append(f'structure("{self.root_name}").')
        super().visitProduct(ctx)

    def visitStructure(self, ctx: ModelParser.StructureContext):
        self.structure_name = ctx.name().getText()
        self.output_asp.append("")
        self.output_asp.append(f'structure("{self.structure_name}").')
        super().visitStructure(ctx)
        self.structure_name = self.root_name

    def visitEnumeration(self, ctx: ModelParser.EnumerationContext):
        self.parent_enum = ctx
        self.output_asp.append("")
        self.output_asp.append(f'enumeration("{ctx.name().getText()}").')
        super().visitEnumeration(ctx)
        self.parent_enum = None

    def visitBehavior(self, ctx: ModelParser.BehaviorContext):
        if ctx.name() is not None:
            self.context = ctx.name().getText()
        super().visitBehavior(ctx)

        self.context = self.root_name

    def visitFeature(self, ctx: ModelParser.FeatureContext):
        field: ModelParser.FieldContext = ctx.field()
        feature_name = field.fieldName.getText()

        if field.number_def() is not None:
            type_name = "num"
        elif field.string_def() is not None:
            return  # ignore string features
        elif field.type_ref is not None:
            type_name = field.type_ref.NAME()
        # else:
        #     type_name = feature_name

        cardinality: ModelParser.CardinalityContext = ctx.cardinality()
        c_min = 1
        c_max = 1
        if cardinality is not None:
            c_min = cardinality.min_.text.replace("x", "")
            c_max = c_min
            if cardinality.max_ is not None:
                c_max = cardinality.max_.text.replace("x", "").replace("*", "#sup")

        self.output_asp.append(f'feature("{self.structure_name}","{feature_name}","{type_name}",{c_min},{c_max}).')
        if type_name == "num":
            num: ModelParser.Number_defContext = field.number_def()
            if num.min_ is not None or num.max_ is not None:
                r_min = "#inf" if num.min_.getText() == "-\u221e" else num.min_.getText()  # negative infinity symbol
                r_max = "#sup" if num.max_.getText() == "\u221e" else num.max_.getText()  # infinity symbol
                self.output_asp.append(f'range("{self.structure_name}","{feature_name}",{r_min},{r_max}).')

    def visitAttribute(self, ctx: ModelParser.AttributeContext):
        # if self.parent_enum is None:
        #     raise ValueError("illegal option")
        parent_name = self.parent_enum.name().getText()
        field: ModelParser.FieldContext = ctx.field()
        if field.number_def() is not None:
            field_type = "num"
        else:
            field_type = "str"
        field_name = field.fieldName.getText()
        self.output_asp.append(f'attribute("{parent_name}","{field_name}","{field_type}").')
        super().visitAttribute(ctx)

    def visitOption(self, ctx: ModelParser.OptionContext):
        # if self.parent_enum is None:
        #     raise ValueError("illegal option")
        parent_name = self.parent_enum.name().getText()
        option_name = ctx.name().getText()
        self.output_asp.append(f'option("{parent_name}", "{option_name}").')

        constant: ModelParser.ConstantContext = ctx.constant()
        if constant != []:
            parent_attr: ModelParser.AttributeContext = self.parent_enum.attribute()
            for a, c in zip(parent_attr, constant):
                field: ModelParser.FieldContext = a.field()
                attr_name = field.fieldName.getText()
                if c.floating() is not None:
                    option_value = c.floating().getText()
                elif c.name() is not None:
                    option_value = f'"{c.name().getText()}"'
                self.output_asp.append(
                    f'attribute_value("{parent_name}","{option_name}","{attr_name}",{option_value}).'
                )

    def visitConditioned(self, ctx: ModelParser.ConditionedContext):
        self.condition_idx = 0
        if ctx.interaction() is None:
            self.output_asp.append("")
            self.output_asp.append(f"behavior({self.constraint_idx}).")
            self.output_asp.append(f'context({self.constraint_idx},"{self.context}").')
            super().visitConditioned(ctx)
            self.constraint_idx += 1

    def visitExplanation(self, ctx: ModelParser.ExplanationContext):
        self.output_asp.append(f"explanation({self.constraint_idx},{ctx.name().getText()}).")
        return super().visitExplanation(ctx)

    def visitAssign_default(self, ctx: ModelParser.Assign_defaultContext):
        path = ctx.path().getText()
        formula = ctx.formula().getText()
        self.output_asp.append(f'default({self.constraint_idx},"{path}","{formula}").')
        super().visitAssign_default(ctx)

    def visitAssign_imply(self, ctx: ModelParser.Assign_implyContext):
        path = ctx.path().getText()
        formula = ctx.formula().getText()
        self.output_asp.append(f'imply({self.constraint_idx},"{path}","{formula}").')
        super().visitAssign_imply(ctx)

    def visitCombinations(self, ctx: ModelParser.CombinationsContext):
        for i, f in enumerate(ctx.formula()):
            self.output_asp.append(f'combinations({self.constraint_idx},{i},"{f.getText()}").')
        super().visitCombinations(ctx)
        self.row_idx = 0

    def visitCombination_row(self, ctx: ModelParser.Combination_rowContext):
        row_type = ctx.rowType.text
        for col_idx, item in enumerate(ctx.combination_item()):
            values = item.getText()
            # Removing brackets around the values. Is this safe?
            if "," in values:
                values = values[1:-1]
            for v in values.split(","):
                if v == "-*-":  # Wildcard operator for combinations table
                    continue
                self.output_asp.append(f'{row_type}({self.constraint_idx},({col_idx},{self.row_idx}),"{v}").')
        self.print_path = False
        super().visitCombination_row(ctx)
        self.print_path = True
        self.row_idx += 1

    def visitPrecondition(self, ctx: ModelParser.PreconditionContext):
        condition = f'"{ctx.condition().getText()}"'
        self.output_asp.append(f"condition({self.constraint_idx},{self.condition_idx},{condition}).")
        self.condition_idx += 1
        super().visitPrecondition(ctx)

    def visitRequire(self, ctx: ModelParser.RequireContext):
        condition = f'"{ctx.condition().getText()}"'
        self.output_asp.append(f"require({self.constraint_idx},{condition}).")
        super().visitRequire(ctx)

    def visitCondition_or(self, ctx: ModelParser.Condition_orContext):
        cond_and: ModelParser.condition_andContext = ctx.condition_and()
        for i in range(len(cond_and) - 1):
            left = cond_and[i].getText()
            right = "||".join([a.getText() for a in cond_and[i + 1 :]])
            complete = left + "||" + right
            self.output_asp.append(f'binary("{complete}","{left}","||","{right}").')
        super().visitCondition_or(ctx)

    def visitCondition_and(self, ctx: ModelParser.Condition_andContext):
        cond_not: ModelParser.condition_notContext = ctx.condition_not()
        for i in range(len(cond_not) - 1):
            left = cond_not[i].getText()
            right = "&&".join([a.getText() for a in cond_not[i + 1 :]])
            complete = left + "&&" + right
            self.output_asp.append(f'binary("{complete}","{left}","&&","{right}").')
        super().visitCondition_and(ctx)

    def visitCondition_not(self, ctx: ModelParser.Condition_notContext):
        complete = ctx.getText()
        if ctx.condition_not() is not None:
            negated = ctx.condition_not().getText()
            self.output_asp.append(f'unary("{complete}","!","{negated}").')
        elif ctx.condition() is not None:
            in_brackets = ctx.condition().getText()
            self.output_asp.append(f'unary("{complete}","()","{in_brackets}").')
        super().visitCondition_not(ctx)

    def visitCondition_compare(self, ctx: ModelParser.Condition_compareContext):
        formula: ModelParser.FormulaContext = ctx.formula()
        parts: ModelParser.Condition_partContext = ctx.condition_part()

        left = formula.getText()
        for i, p in enumerate(parts):
            # Binary atom for compare
            right = p.formula().getText()
            compare = p.compare().getText()
            complete = left + compare + right
            self.output_asp.append(f'binary("{complete}","{left}","{compare}","{right}").')
            left = right

            # # For multiple comparisons rewrite as propositional formulas connected by &&
            # right_prop = "&&".join(
            #     [f"{l.formula().getText()}{r.getText()}" for l, r in (zip(parts[i:], parts[i + 1 :]))]
            # )
            # if right_prop != "":
            #     complete_prop = complete + "&&" + right_prop
            #     self.output_asp.append(f'binary("{complete_prop}","{complete}","&&","{right_prop}").')
        super().visitCondition_compare(ctx)

    def visitFormula_add(self, ctx: ModelParser.Formula_addContext):
        form_sub: ModelParser.Formula_subContext = ctx.formula_sub()
        for i in range(len(form_sub) - 1):
            left = form_sub[i].getText()
            right = "+".join([a.getText() for a in form_sub[i + 1 :]])
            complete = left + "+" + right
            self.output_asp.append(f'binary("{complete}","{left}","+","{right}").')
        super().visitFormula_add(ctx)

    def visitFormula_sub(self, ctx: ModelParser.Formula_subContext):
        form_mul: ModelParser.Formula_mulContext = ctx.formula_mul()
        for i in range(len(form_mul) - 1):
            left = form_mul[i].getText()
            right = "-".join([a.getText() for a in form_mul[i + 1 :]])
            complete = left + "-" + right
            self.output_asp.append(f'binary("{complete}","{left}","-","{right}").')
        super().visitFormula_sub(ctx)

    def visitFormula_mul(self, ctx: ModelParser.Formula_mulContext):
        form_div: ModelParser.Formula_divContext = ctx.formula_div()
        for i in range(len(form_div) - 1):
            left = form_div[i].getText()
            right = "*".join([a.getText() for a in form_div[i + 1 :]])
            complete = left + "*" + right
            self.output_asp.append(f'binary("{complete}","{left}","*","{right}").')
        super().visitFormula_mul(ctx)

    def visitFormula_div(self, ctx: ModelParser.Formula_divContext):
        form_pow: ModelParser.Formula_powContext = ctx.formula_pow()
        for i in range(len(form_pow) - 1):
            left = form_pow[i].getText()
            right = "/".join([a.getText() for a in form_pow[i + 1 :]])
            complete = left + "/" + right
            self.output_asp.append(f'binary("{complete}","{left}","/","{right}").')
        super().visitFormula_div(ctx)

    def visitFormula_pow(self, ctx: ModelParser.Formula_powContext):
        form_sign: ModelParser.Formula_signContext = ctx.formula_sign()
        for i in range(len(form_sign) - 1):
            left = form_sign[i].getText()
            right = "^".join([a.getText() for a in form_sign[i + 1 :]])
            complete = left + "^" + right
            self.output_asp.append(f'binary("{complete}","{left}","^","{right}").')
        super().visitFormula_pow(ctx)

    def visitFormula_sign(self, ctx: ModelParser.Formula_signContext):
        complete = ctx.getText()
        if ctx.formula_sign() is not None:
            if ctx.neg is not None:
                negated = ctx.formula_sign().getText()
                self.output_asp.append(f'unary("{complete}","-","{negated}").')
            else:
                # Is this really necessary?
                positive = ctx.formula_sign().getText()
                self.output_asp.append(f'unary("{complete}","+","{positive}").')
        elif ctx.formula() is not None:
            in_brackets = ctx.formula().getText()
            self.output_asp.append(f'unary("{complete}","()","{in_brackets}").')
        elif ctx.formula_func() is not None:
            func = ctx.formula_func().FUNCTION()
            for f in ctx.formula_func().formula():
                if str(func) in ["sum", "count", "min", "max", "avg"]:
                    self.output_asp.append(f'function("{self.context}","{complete}","{func}","{f.getText()}").')
                else:
                    self.output_asp.append(f'unary("{complete}","{func}","{f.getText()}").')
        super().visitFormula_sign(ctx)

    def visitPath(self, ctx: ModelParser.PathContext):
        # Only do this for actual paths? Not formulas
        if self.print_path:
            full_path = f"{ctx.getText()}"

            if full_path[0].isupper():
                self.output_asp.append(f'constant("{full_path}").')
            else:
                for i, p in enumerate(ctx.path_item()):
                    self.output_asp.append(f'path("{full_path}",{i},"{p.getText()}").')

    def visitFloating(self, ctx: ModelParser.FloatingContext):
        # if ctx.FLOATING() is not None:
        #     pass
        if ctx.INTEGER() is not None:
            self.output_asp.append(f'number("{ctx.INTEGER()}",{ctx.INTEGER()}).')

from dataclasses import dataclass, field


@dataclass
class COOMEnumeration:
    """Dataclass representing a coom enumeration."""
    name: str
    options: list[str] = field(default_factory=list)
    attributes: {str, str} = field(default_factory=dict)
    interpretations: {str, list[str]} = field(default_factory=dict)  # Values for each attribute

    # attribute_functions: {str, str} = field(default_factory=dict)  # Used to store the function name of each attribute

    def add_option(self, option: str):
        self.options.append(option)

    def add_attribute(self, name, type_):
        self.attributes[name] = type_
        self.interpretations[name] = []

    def add_interpretation(self, attribute, option, value):
        self.interpretations[attribute].append(value)

    def to_fodot_voc(self):
        # Declare the enumeration as a type with functions for the attributes.
        decls = [f'type {self.name} := {{{", ".join(self.options)}}}']  # type decl
        for attribute in self.attributes:
            type_ = self.attributes[attribute]
            type_ = 'Int' if type_ == 'num' else type_
            decls.append(f'{self.name}_{attribute}: {self.name} -> {type_}')
            # self.attribute_functions[attribute] = f'{self.name}_{attribute}'
        return decls

    def to_fodot_struc(self):
        # Generate a fodot interpretation for each attribute.
        interps = []
        for attribute in self.attributes:
            interp = []
            for elem, value in zip(self.options, self.interpretations[attribute]):
                interp.append(f'{elem} -> {value}')
            interps.append(f'{self.name}_{attribute} := {{{", ".join(interp)}}}.')
        return interps


@dataclass
class COOMFeature:
    """ Dataclass representing a coom feature."""
    name: str
    type_: str
    lcard: int = 1  # lower cardinality
    ucard: int = 1  # upper cardinality

    def max_card(self):
        return int(self.ucard) if self.ucard != '#sup' else 10  #TODO: change default

    def min_card(self):
        return 1 if self.ucard == self.lcard == 1 else 0

    def to_decl(self, input_types, enumerations, structures):
        """
        Recursively generate the declaration of this feature and all its subfeatures

        Returns the variables, the name, somethng else probably
        """
        if self.type_ == 'num':
            # Easy
            return [(self.name, input_types, self.type_)]
        elif self.type_ in enumerations:
            # Also easy
            return [(self.name, input_types, self.type_)]
        else:
            # type is structure. Complex. :-(
            decls = []
            for feat in structures[self.type_].features:
                res_tuple = feat.to_decl(input_types, enumerations, structures)
                for res in res_tuple:
                    decls.append((f'{self.name}_{res[0]}', res[1], res[2]))
            return decls

@dataclass
class COOMStructure:
    """ Dataclass representing a coom structure."""
    name: str
    features: list[COOMFeature] = field(default_factory=list)

    def add_feature(self, feature):
        self.features.append(feature)

# from enum import Enum
# 
# 
# class COOMOperatorEnum(Enum):
#     # Operators in FO(.) format.
#     EQ = '='
#     GT = '>'
#     GE = '>='
#     LT = '<'
#     LE = '=<'
#     NEQ = '~='
# 
#     @staticmethod
#     def from_str(oper):
#         match oper:
#             case '=':
#                 return COOMOperatorEnum.EQ
#             case '>':
#                 return COOMOperatorEnum.GT
#             case '>=':
#                 return COOMOperatorEnum.GE
#             case '<':
#                 return COOMOperatorEnum.LT
#             case '<=':
#                 return COOMOperatorEnum.LE
#             case '!=':
#                 return COOMOperatorEnum.NEQ
# 
# 
# 
# @dataclass
# class COOMPath:
#     """ Dataclass representing a coom path. """
#     child: COOMFeature | COOMPath
# 
# @dataclass
# class COOMComparison:
#     """ Dataclass representing a coom comparison. """
#     left: str | COOMFeature
#     right = str | COOMFeature
#     operator: COOMOperatorEnum
# 
# @dataclass
# class COOMRequire:
#     """ Dataclass representing a coom require. """
#     require: COOMComparison
#     condition: COOMComparison | None = None
#     explanation: str | None = None
# 
# @dataclass
# class COOMCombinations:
#     """ Dataclass representing a COOM. """
# 
# 
# @dataclass
# class COOMBehavior:
#     """" Dataclass representing a behavior. """
#     name: str = ''
#     constraints: list[COOMRequire | COOMCombinations] = field(default_factory=list)



class IDPModelVisitor(ModelVisitor):
    """
    Custom visitor of the COOM Parser.
    Generates a list of ASP facts as strings.
    """

    def __init__(self) -> None:
        super().__init__()
        self.parent_enum: Optional[ModelParser.EnumerationContext] = None
        self.root_name: str = "product"
        self.structure_name: str = self.root_name
        self.context: str = self.root_name
        self.constraint_idx: int = 0
        self.condition_idx: int = 0
        self.row_idx: int = 0
        self.print_path: bool = True
        self.output_asp: List[str] = []

        # Datastructures to create a Pythonic model of the COOM file.
        self.enumerations: dict(str, COOMEnumeration) = {}
        self.structures: dict(str, COOMStructure) = {}
        self.features: dict(str, COOMFeature) = {}

        self.open_terms: list[str] = []  # used to puzzle together formulas in FO(.) form.
        self.formulas: list[str] = []  # finalized formulas in FO(.) form.

    def kb(self):
        # Generate KB
        print(self.enumerations)
        print(self.structures)
        print(self.features)

        voc = ['vocabulary {']
        for enum in self.enumerations.values():
            voc += enum.to_fodot_voc()

        for name, feat in self.features.items():
            if feat.type_ == 'num':
                # Easy translation
                voc.append(f'{feat.name}: -> Int')
            elif feat.type_ in self.enumerations or feat.type_ == 'Bool':
                # Easy translation
                voc.append(f'{feat.name}: -> {feat.type_}')
            else:
                # Mappings on structures are complex :-(.
                # First, introduce type for the ID
                voc.append(f'type {feat.name}_id := {{{feat.min_card()}..{feat.max_card()}}}')

                # Then, the domain predicate.
                voc.append(f'{feat.name}_included: {feat.name}_id -> Bool')

                # Finally, the functions representing
                for subfeat in self.structures[feat.type_].features:
                    res_list = subfeat.to_decl([f'{feat.name}_id'], self.enumerations, self.structures)
                    for res in res_list:
                        voc.append(f'{feat.name}_{res[0]}: {"*".join(res[1])} -> {res[2]}'
                                   f' (domain: {feat.name}_included)')
        print('\n\t'.join(voc) + '\n}')

        formulas = "\n\t".join((f'{x}.' for x in self.formulas))
        print(f'theory {{\n {formulas}\n }}')

        struc = ['structure {']
        for enum in self.enumerations.values():
            struc += enum.to_fodot_struc()
        print('\n\t'.join(struc) + '\n}')

        print('procedure main() { pretty_print(model_expand(T,S))}')


    def visitProduct(self, ctx: ModelParser.ProductContext):
        self.output_asp.append(f'structure("{self.root_name}").')
        super().visitProduct(ctx)

    def visitStructure(self, ctx: ModelParser.StructureContext):
        self.structure_name = ctx.name().getText()
        self.output_asp.append("")
        self.output_asp.append(f'structure("{self.structure_name}").')

        struc = COOMStructure(name=self.structure_name)
        self.structures[self.structure_name] = struc

        super().visitStructure(ctx)

        self.structure_name = self.root_name


    def visitEnumeration(self, ctx: ModelParser.EnumerationContext):
        self.parent_enum = ctx
        self.output_asp.append("")
        self.output_asp.append(f'enumeration("{ctx.name().getText()}").')

        enum = COOMEnumeration(name=ctx.name().getText())
        self.enumerations[ctx.name().getText()] = enum
        super().visitEnumeration(ctx)

        self.parent_enum = None

    def visitBehavior(self, ctx: ModelParser.BehaviorContext):
        if ctx.name() is not None:
            self.context = ctx.name().getText()
        super().visitBehavior(ctx)

        self.context = self.root_name

    def visitFeature(self, ctx: ModelParser.FeatureContext):
        field: ModelParser.FieldContext = ctx.field()
        feature_name = field.fieldName.getText()

        if field.number_def() is not None:
            type_name = "num"
        elif field.string_def() is not None:
            return  # ignore string features
        elif field.type_ref is not None:
            type_name = field.type_ref.NAME()
        # else:
        #     type_name = feature_name

        cardinality: ModelParser.CardinalityContext = ctx.cardinality()
        c_min = 1
        c_max = 1
        if cardinality is not None:
            c_min = cardinality.min.text.replace("x", "")
            c_max = c_min
            if cardinality.max is not None:
                c_max = cardinality.max.text.replace("x", "").replace("*", "#sup")

        self.output_asp.append(f'feature("{self.structure_name}","{feature_name}","{type_name}",{c_min},{c_max}).')
        if type_name == "num":
            num: ModelParser.Number_defContext = field.number_def()
            if num.min is not None or num.max is not None:
                r_min = "#inf" if num.min.getText() == "-\u221e" else num.min.getText()  # negative infinity symbol
                r_max = "#sup" if num.max.getText() == "\u221e" else num.max.getText()  # infinity symbol
                self.output_asp.append(f'range("{self.structure_name}","{feature_name}",{r_min},{r_max}).')

        feature = COOMFeature(name=str(feature_name), type_=str(type_name), lcard=c_min, ucard=c_max)
        if self.structure_name == 'product':
            self.features[feature_name] = feature
        else:
            self.structures[self.structure_name].add_feature(feature)

    def visitAttribute(self, ctx: ModelParser.AttributeContext):
        # if self.parent_enum is None:
        #     raise ValueError("illegal option")
        parent_name = self.parent_enum.name().getText()
        field: ModelParser.FieldContext = ctx.field()
        if field.number_def() is not None:
            field_type = "num"
        else:
            field_type = "str"
        field_name = field.fieldName.getText()
        self.output_asp.append(f'attribute("{parent_name}","{field_name}","{field_type}").')
        self.enumerations[parent_name].add_attribute(field_name, field_type)
        super().visitAttribute(ctx)

    def visitOption(self, ctx: ModelParser.OptionContext):
        # if self.parent_enum is None:
        #     raise ValueError("illegal option")
        parent_name = self.parent_enum.name().getText()
        option_name = ctx.name().getText()
        self.output_asp.append(f'option("{parent_name}", "{option_name}").')
        self.enumerations[parent_name].add_option(option_name)

        constant: ModelParser.ConstantContext = ctx.constant()
        if constant != []:
            parent_attr: ModelParser.AttributeContext = self.parent_enum.attribute()
            for a, c in zip(parent_attr, constant):
                field: ModelParser.FieldContext = a.field()
                attr_name = field.fieldName.getText()
                if c.floating() is not None:
                    option_value = c.floating().getText()
                elif c.name() is not None:
                    option_value = f'"{c.name().getText()}"'
                self.output_asp.append(
                    f'attribute_value("{parent_name}","{option_name}","{attr_name}",{option_value}).'
                )
                self.enumerations[parent_name].add_interpretation(attr_name, option_name, option_value)

    def visitConditioned(self, ctx: ModelParser.ConditionedContext):
        self.condition_idx = 0
        if ctx.interaction() is None:
            self.output_asp.append("")
            self.output_asp.append(f"behavior({self.constraint_idx}).")
            self.output_asp.append(f'context({self.constraint_idx},"{self.context}").')
            super().visitConditioned(ctx)
            self.constraint_idx += 1

    def visitExplanation(self, ctx: ModelParser.ExplanationContext):
        self.output_asp.append(f"explanation({self.constraint_idx},{ctx.name().getText()}).")
        return super().visitExplanation(ctx)

    def visitAssign_default(self, ctx: ModelParser.Assign_defaultContext):
        path = ctx.path().getText()
        formula = ctx.formula().getText()
        self.output_asp.append(f'default({self.constraint_idx},"{path}","{formula}").')
        super().visitAssign_default(ctx)

    def visitAssign_imply(self, ctx: ModelParser.Assign_implyContext):
        path = ctx.path().getText()
        formula = ctx.formula().getText()
        self.output_asp.append(f'imply({self.constraint_idx},"{path}","{formula}").')
        super().visitAssign_imply(ctx)

    def visitCombinations(self, ctx: ModelParser.CombinationsContext):
        for i, f in enumerate(ctx.formula()):
            self.output_asp.append(f'combinations({self.constraint_idx},{i},"{f.getText()}").')
        self.open_terms = []  # Clear open terms (TODO: this should warn about unused terms).
        super().visitCombinations(ctx)
        columns = int(len(self.open_terms)/(self.row_idx + 1))

        terms = []
        symbols = self.open_terms[0:columns]
        for i in range(1, self.row_idx+1):
            values = self.open_terms[columns*i:columns*(i+1)]
            term = []
            for (symbol, value) in zip(symbols, values):
                if value == 'True':
                    term.append(f'{symbol}')
                elif value == 'False':
                    term.append(f'~{symbol}')
                else:
                    term.append(f'{symbol} in {{{value}}}')
            terms.append('(' + ' & '.join(term) + ')')

        self.formulas.append(' | '.join(terms))

        self.open_terms = [] 
        self.row_idx = 0

    def visitCombination_row(self, ctx: ModelParser.Combination_rowContext):
        row_type = ctx.rowType.text
        for col_idx, item in enumerate(ctx.combination_item()):
            values = item.getText()
            # Removing brackets around the values. Is this safe?
            if "," in values:
                values = values[1:-1]
            for v in values.split(","):
                if v == "-*-":  # Wildcard operator for combinations table
                    continue
                self.output_asp.append(f'{row_type}({self.constraint_idx},({col_idx},{self.row_idx}),"{v}").')
            self.open_terms.append(values)
        self.print_path = False
        super().visitCombination_row(ctx)
        self.print_path = True
        self.row_idx += 1

    def visitPrecondition(self, ctx: ModelParser.PreconditionContext):
        condition = f'"{ctx.condition().getText()}"'
        self.output_asp.append(f"condition({self.constraint_idx},{self.condition_idx},{condition}).")
        self.condition_idx += 1
        super().visitPrecondition(ctx)

    def visitRequire(self, ctx: ModelParser.RequireContext):
        super().visitRequire(ctx)
        condition = f'"{ctx.condition().getText()}"'
        self.output_asp.append(f"require({self.constraint_idx},{condition}).")

        if len(self.open_terms) == 2:
            term = f'{self.open_terms[-2]} => {self.open_terms[-1]}'
            self.open_terms.pop()
            self.open_terms.pop()
            self.formulas.append(term)
        elif len(self.open_terms) == 1:
            term = f'{self.open_terms[-1]}'  # Require with no condition
            self.open_terms.pop()
            self.formulas.append(term)
        else:
            print(f'Warning: unused open term {self.open_terms}')

    def visitCondition_or(self, ctx: ModelParser.Condition_orContext):
        cond_and: ModelParser.condition_andContext = ctx.condition_and()
        for i in range(len(cond_and) - 1):
            left = cond_and[i].getText()
            right = "||".join([a.getText() for a in cond_and[i + 1 :]])
            complete = left + "||" + right
            self.output_asp.append(f'binary("{complete}","{left}","||","{right}").')
        super().visitCondition_or(ctx)

    def visitCondition_and(self, ctx: ModelParser.Condition_andContext):
        cond_not: ModelParser.condition_notContext = ctx.condition_not()
        for i in range(len(cond_not) - 1):
            left = cond_not[i].getText()
            right = "&&".join([a.getText() for a in cond_not[i + 1 :]])
            complete = left + "&&" + right
            self.output_asp.append(f'binary("{complete}","{left}","&&","{right}").')
        super().visitCondition_and(ctx)

    def visitCondition_not(self, ctx: ModelParser.Condition_notContext):
        complete = ctx.getText()
        if ctx.condition_not() is not None:
            negated = ctx.condition_not().getText()
            self.output_asp.append(f'unary("{complete}","!","{negated}").')
        elif ctx.condition() is not None:
            in_brackets = ctx.condition().getText()
            self.output_asp.append(f'unary("{complete}","()","{in_brackets}").')
        super().visitCondition_not(ctx)

    def visitCondition_compare(self, ctx: ModelParser.Condition_compareContext):
        formula: ModelParser.FormulaContext = ctx.formula()
        parts: ModelParser.Condition_partContext = ctx.condition_part()

        super().visitCondition_compare(ctx)
        left = formula.getText()
        for i, p in enumerate(parts):
            # Binary atom for compare
            right = p.formula().getText()
            compare = p.compare().getText()
            complete = left + compare + right
            self.output_asp.append(f'binary("{complete}","{left}","{compare}","{right}").')

            left = right

            # # For multiple comparisons rewrite as propositional formulas connected by &&
            # right_prop = "&&".join(
            #     [f"{l.formula().getText()}{r.getText()}" for l, r in (zip(parts[i:], parts[i + 1 :]))]
            # )
            # if right_prop != "":
            #     complete_prop = complete + "&&" + right_prop
            #     self.output_asp.append(f'binary("{complete_prop}","{complete}","&&","{right_prop}").')

            # TODO: reimplement open_terms using LIFO?
            term = f'{self.open_terms[-2]} {compare} {self.open_terms[-1]}'
            self.open_terms.pop()
            self.open_terms.pop()
            self.open_terms.append(term)

    def visitFormula_add(self, ctx: ModelParser.Formula_addContext):
        form_sub: ModelParser.Formula_subContext = ctx.formula_sub()
        for i in range(len(form_sub) - 1):
            left = form_sub[i].getText()
            right = "+".join([a.getText() for a in form_sub[i + 1 :]])
            complete = left + "+" + right
            self.output_asp.append(f'binary("{complete}","{left}","+","{right}").')
        super().visitFormula_add(ctx)

    def visitFormula_sub(self, ctx: ModelParser.Formula_subContext):
        form_mul: ModelParser.Formula_mulContext = ctx.formula_mul()
        for i in range(len(form_mul) - 1):
            left = form_mul[i].getText()
            right = "-".join([a.getText() for a in form_mul[i + 1 :]])
            complete = left + "-" + right
            self.output_asp.append(f'binary("{complete}","{left}","-","{right}").')
        super().visitFormula_sub(ctx)

    def visitFormula_mul(self, ctx: ModelParser.Formula_mulContext):
        form_div: ModelParser.Formula_divContext = ctx.formula_div()
        for i in range(len(form_div) - 1):
            left = form_div[i].getText()
            right = "*".join([a.getText() for a in form_div[i + 1 :]])
            complete = left + "*" + right
            self.output_asp.append(f'binary("{complete}","{left}","*","{right}").')
        super().visitFormula_mul(ctx)

    def visitFormula_div(self, ctx: ModelParser.Formula_divContext):
        form_pow: ModelParser.Formula_powContext = ctx.formula_pow()
        for i in range(len(form_pow) - 1):
            left = form_pow[i].getText()
            right = "/".join([a.getText() for a in form_pow[i + 1 :]])
            complete = left + "/" + right
            self.output_asp.append(f'binary("{complete}","{left}","/","{right}").')
        super().visitFormula_div(ctx)

    def visitFormula_pow(self, ctx: ModelParser.Formula_powContext):
        form_sign: ModelParser.Formula_signContext = ctx.formula_sign()
        for i in range(len(form_sign) - 1):
            left = form_sign[i].getText()
            right = "^".join([a.getText() for a in form_sign[i + 1 :]])
            complete = left + "^" + right
            self.output_asp.append(f'binary("{complete}","{left}","^","{right}").')
        super().visitFormula_pow(ctx)

    def visitFormula_sign(self, ctx: ModelParser.Formula_signContext):
        complete = ctx.getText()
        if ctx.formula_sign() is not None:
            if ctx.neg is not None:
                negated = ctx.formula_sign().getText()
                self.output_asp.append(f'unary("{complete}","-","{negated}").')
            else:
                # Is this really necessary?
                positive = ctx.formula_sign().getText()
                self.output_asp.append(f'unary("{complete}","+","{positive}").')
        elif ctx.formula() is not None:
            in_brackets = ctx.formula().getText()
            self.output_asp.append(f'unary("{complete}","()","{in_brackets}").')
        elif ctx.formula_func() is not None:
            func = ctx.formula_func().FUNCTION()
            for f in ctx.formula_func().formula():
                if str(func) in ["sum", "count", "min", "max", "avg"]:
                    self.output_asp.append(f'function("{self.context}","{complete}","{func}","{f.getText()}").')
                else:
                    self.output_asp.append(f'unary("{complete}","{func}","{f.getText()}").')
        super().visitFormula_sign(ctx)

    def visitPath(self, ctx: ModelParser.PathContext):
        # Only do this for actual paths? Not formulas
        if self.print_path:
            full_path = f"{ctx.getText()}"

            if full_path[0].isupper():
                self.output_asp.append(f'constant("{full_path}").')
            else:
                for i, p in enumerate(ctx.path_item()):
                    self.output_asp.append(f'path("{full_path}",{i},"{p.getText()}").')
        else:
            return
        full_path = full_path.split('.')
        if len(full_path) == 1:
            # Straightforward constant or enum element.
            if (symbol:=full_path[0]) in self.features:
                # Feature translated to applied symbol
                self.open_terms.append(f'{symbol}()')
            else:
                # Enum element translated to type element.
                self.open_terms.append(f'{symbol}')
        else:
            current_type = None  # This tracks the current type of the symbol in the path.
                                 # I.e., for "frontWheel.size", the current_type of `size` would be `Wheel`

            full_fodot = ''
            for symbol in full_path:
                if current_type is None:
                    # First symbol of path can always be translated directly.
                    if symbol in self.features:
                        full_fodot = f'{symbol}()'
                        current_type = self.features[symbol].type_
                        continue
                    else:
                        # This is impossible?
                        raise NotImplementedError()
                else:
                    # full_symbol = f'{current_type}_{symbol}'
                    if current_type in self.features:
                        # This is impossible?
                        raise NotImplementedError()
                    elif current_type in self.enumerations:
                        # Symbol is attribute of an enumeration
                        full_fodot = f'{current_type}_{symbol}({full_fodot})'
                    else:
                        # In structures
                        raise NotImplementedError()
                    # breakpoint()

            self.open_terms.append(full_fodot)

    def visitFloating(self, ctx: ModelParser.FloatingContext):
        # if ctx.FLOATING() is not None:
        #     pass
        if ctx.INTEGER() is not None:
            self.output_asp.append(f'number("{ctx.INTEGER()}",{ctx.INTEGER()}).')

            self.open_terms.append(str(ctx.INTEGER()))
